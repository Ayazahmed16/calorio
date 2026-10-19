"""Clients for external services: USDA FoodData Central, TheMealDB, Fitbit, Telegram.

Every client is optional and fails soft: network problems or missing keys raise ApiError / return empty
results, and the views turn that into a clear message instead of a crash.
"""
import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

UA = 'Calorio/1.0 (calorie tracker)'


class ApiError(Exception):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def http_json(url, *, method='GET', headers=None, data=None, form=None, timeout=8):
    body = None
    h = {'User-Agent': UA, 'Accept': 'application/json', **(headers or {})}
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h['Content-Type'] = 'application/x-www-form-urlencoded'
    elif data is not None:
        body = json.dumps(data).encode()
        h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https hosts defined below
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode('utf-8')[:300]
        except Exception:      # noqa: BLE001
            detail = ''
        raise ApiError(f'HTTP {e.code} {detail}', status=e.code) from e
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise ApiError(f'Network error: {e}') from e


def _https(url):
    url = (url or '').strip()
    return url if url.startswith('https://') and len(url) <= 500 else ''


# ===================================================================== USDA

USDA_URL = 'https://api.nal.usda.gov/fdc/v1/foods/search'


def usda_search(query, limit=6):
    """Generic foods with accurate per-100 g macros (Foundation + SR Legacy datasets)."""
    query = (query or '').strip()
    if len(query) < 2:
        return []
    ck = 'usda:' + query.lower()
    hit = cache.get(ck)
    if hit is not None:
        return hit[:limit]
    params = {'api_key': settings.USDA_API_KEY, 'query': query, 'pageSize': 15,
              'dataType': 'Foundation,SR Legacy'}
    try:
        data = http_json(f'{USDA_URL}?{urllib.parse.urlencode(params)}', timeout=6)
    except ApiError:
        return []
    out = []
    for f in data.get('foods', []):
        n = {str(x.get('nutrientNumber')): x.get('value') for x in f.get('foodNutrients', [])}
        kcal = n.get('208') or n.get('957') or n.get('958')
        if not kcal:
            continue
        name = (f.get('description') or '').strip()
        if not name:
            continue
        out.append({
            'name': name[:100], 'calories': round(float(kcal), 1),
            'protein': round(float(n.get('203') or 0), 1), 'carbs': round(float(n.get('205') or 0), 1),
            'fat': round(float(n.get('204') or 0), 1), 'barcode': '', 'image': '', 'source': 'USDA',
        })
    out.sort(key=lambda r: len(r['name']))              # "Bananas, raw" before long preparation variants
    cache.set(ck, out, 3600)
    return out[:limit]


def search_all(query, limit=8):
    """USDA (generic foods) and Open Food Facts (packaged products), fetched in parallel and interleaved."""
    from . import services
    with ThreadPoolExecutor(max_workers=2) as pool:
        usda_f = pool.submit(usda_search, query, 5)
        off_f = pool.submit(services.search_foods, query, 5)
        usda, off = usda_f.result(), off_f.result()
    for r in off:
        r.setdefault('source', 'Open Food Facts')
    merged, seen = [], set()
    for r in usda[:4] + off[:4] + usda[4:] + off[4:]:
        key = r['name'].lower()
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return merged[:limit]


# ================================================================= TheMealDB

MEALDB = 'https://www.themealdb.com/api/json/v1/1'


def _mealdb(path):
    ck = 'mealdb:' + path
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = http_json(f'{MEALDB}/{path}', timeout=8)
    cache.set(ck, data, 3600)
    return data


def _meal_summary(m):
    thumb = _https(m.get('strMealThumb'))
    return {'id': m.get('idMeal'), 'name': m.get('strMeal'), 'thumb': thumb + '/preview' if thumb else '',
            'category': m.get('strCategory') or '', 'area': m.get('strArea') or ''}


def meal_search(query):
    data = _mealdb('search.php?' + urllib.parse.urlencode({'s': query}))
    return [_meal_summary(m) for m in (data.get('meals') or [])][:24]


def meal_categories():
    data = _mealdb('list.php?c=list')
    return sorted(m['strCategory'] for m in (data.get('meals') or []))


def meal_by_category(category):
    data = _mealdb('filter.php?' + urllib.parse.urlencode({'c': category}))
    return [{'id': m['idMeal'], 'name': m['strMeal'], 'category': category, 'area': '',
             'thumb': (_https(m.get('strMealThumb')) + '/preview') if _https(m.get('strMealThumb')) else ''}
            for m in (data.get('meals') or [])][:24]


def meal_detail(meal_id):
    meal_id = ''.join(ch for ch in str(meal_id) if ch.isdigit())[:10]
    if not meal_id:
        return None
    data = _mealdb('lookup.php?' + urllib.parse.urlencode({'i': meal_id}))
    meals = data.get('meals') or []
    if not meals:
        return None
    m = meals[0]
    ingredients = []
    for i in range(1, 21):
        name = (m.get(f'strIngredient{i}') or '').strip()
        if name:
            ingredients.append({'name': name, 'measure': (m.get(f'strMeasure{i}') or '').strip()})
    detail = _meal_summary(m)
    detail.update({
        'image': _https(m.get('strMealThumb')),
        'instructions': [s.strip() for s in (m.get('strInstructions') or '').replace('\r', '').split('\n') if s.strip()],
        'ingredients': ingredients, 'youtube': _https(m.get('strYoutube')), 'source': _https(m.get('strSource')),
    })
    return detail


def meal_random():
    data = http_json(f'{MEALDB}/random.php', timeout=8)      # not cached: should differ each time
    return [_meal_summary(m) for m in (data.get('meals') or [])]


# ===================================================================== Fitbit

FITBIT_AUTH = 'https://www.fitbit.com/oauth2/authorize'
FITBIT_TOKEN = 'https://api.fitbit.com/oauth2/token'
FITBIT_API = 'https://api.fitbit.com'


def fitbit_configured():
    return bool(settings.FITBIT_CLIENT_ID and settings.FITBIT_CLIENT_SECRET)


def new_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return verifier, challenge


def fitbit_auth_url(redirect_uri, state, challenge):
    return FITBIT_AUTH + '?' + urllib.parse.urlencode({
        'response_type': 'code', 'client_id': settings.FITBIT_CLIENT_ID, 'redirect_uri': redirect_uri,
        'scope': 'activity weight', 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
    })


def _basic():
    raw = f'{settings.FITBIT_CLIENT_ID}:{settings.FITBIT_CLIENT_SECRET}'.encode()
    return {'Authorization': 'Basic ' + base64.b64encode(raw).decode()}


def fitbit_exchange(code, verifier, redirect_uri):
    return http_json(FITBIT_TOKEN, method='POST', headers=_basic(), form={
        'client_id': settings.FITBIT_CLIENT_ID, 'grant_type': 'authorization_code', 'code': code,
        'code_verifier': verifier, 'redirect_uri': redirect_uri})


def _store_tokens(conn, tok):
    conn.access_token = tok['access_token']
    conn.refresh_token = tok.get('refresh_token', conn.refresh_token)
    conn.expires_at = timezone.now() + timedelta(seconds=int(tok.get('expires_in', 28800)))
    if tok.get('user_id'):
        conn.fitbit_user_id = tok['user_id']
    conn.save()


def fitbit_refresh(conn):
    tok = http_json(FITBIT_TOKEN, method='POST', headers=_basic(),
                    form={'grant_type': 'refresh_token', 'refresh_token': conn.refresh_token})
    _store_tokens(conn, tok)


def fitbit_get(conn, path):
    if conn.expires_at - timedelta(seconds=60) <= timezone.now():
        fitbit_refresh(conn)
    # fr_FR makes Fitbit return metric units (kg), regardless of the account's display units
    headers = {'Authorization': f'Bearer {conn.access_token}', 'Accept-Language': 'fr_FR'}
    try:
        return http_json(FITBIT_API + path, headers=headers)
    except ApiError as e:
        if e.status == 401:                      # token revoked/expired early: refresh once and retry
            fitbit_refresh(conn)
            headers['Authorization'] = f'Bearer {conn.access_token}'
            return http_json(FITBIT_API + path, headers=headers)
        raise


def fitbit_sync(conn, days=7):
    """Pull steps, calories burned and weight for the last `days` days into Calorio."""
    from .models import ActivityEntry, WeightEntry
    today = timezone.localdate()
    synced_days = 0
    for i in range(days):
        day = today - timedelta(days=i)
        summary = fitbit_get(conn, f'/1/user/-/activities/date/{day.isoformat()}.json').get('summary', {})
        steps, burned = int(summary.get('steps') or 0), float(summary.get('caloriesOut') or 0)
        if steps or burned:
            ActivityEntry.objects.update_or_create(
                user=conn.user, date=day,
                defaults={'steps': steps, 'calories_burned': round(burned, 1)})
            ActivityEntry.objects.filter(user=conn.user, date=day, activity_type='').update(activity_type='Fitbit')
            synced_days += 1
    start = today - timedelta(days=days - 1)
    weights = 0
    data = fitbit_get(conn, f'/1/user/-/body/log/weight/date/{start.isoformat()}/{today.isoformat()}.json')
    for w in data.get('weight', []):
        try:
            kg = round(float(w['weight']), 1)
            d = datetime.strptime(w['date'], '%Y-%m-%d').date()
        except (KeyError, ValueError, TypeError):
            continue
        if 20 <= kg <= 400:
            WeightEntry.objects.update_or_create(user=conn.user, date=d, defaults={'weight_kg': kg})
            weights += 1
    conn.last_synced = timezone.now()
    conn.save(update_fields=['last_synced'])
    return {'days': synced_days, 'weights': weights}


# ================================================================== Telegram

def telegram_configured():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def tg_api(method, payload):
    return http_json(f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}', method='POST',
                     data=payload, timeout=12)


def tg_send(chat_id, text):
    try:
        tg_api('sendMessage', {'chat_id': chat_id, 'text': text})
        return True
    except ApiError:
        return False


def day_summary_text(user, day=None):
    from .models import ActivityEntry, DailyGoal, MealEntry, WaterLog
    day = day or timezone.localdate()
    meals = list(MealEntry.objects.filter(user=user, date=day).select_related('food'))
    goal, _ = DailyGoal.objects.get_or_create(user=user)
    cal = round(sum(m.total_calories() for m in meals))
    protein = round(sum(m.total_protein() for m in meals))
    act = ActivityEntry.objects.filter(user=user, date=day).first()
    water = WaterLog.objects.filter(user=user, date=day).first()
    return (f'Today so far:\n'
            f'Calories: {cal} / {round(goal.target_calories)}\n'
            f'Protein: {protein} / {round(goal.target_protein)} g\n'
            f'Steps: {act.steps if act else 0} / {goal.target_steps}\n'
            f'Water: {water.amount_ml if water else 0} / {goal.target_water_ml} ml')


def tg_handle_update(update):
    """Process one Telegram update: account linking and a couple of quick commands."""
    from .models import UserSettings, WaterLog
    msg = update.get('message') or {}
    text = (msg.get('text') or '').strip()
    chat_id = str((msg.get('chat') or {}).get('id') or '')
    if not chat_id or not text.startswith('/'):
        return None
    cmd, _, arg = text.partition(' ')
    cmd = cmd.split('@')[0].lower()
    arg = arg.strip()

    if cmd == '/start':
        us = UserSettings.objects.filter(telegram_link_code=arg).exclude(telegram_link_code='').first() if arg else None
        if us:
            UserSettings.objects.filter(telegram_chat_id=chat_id).exclude(pk=us.pk).update(telegram_chat_id='')
            us.telegram_chat_id, us.telegram_link_code = chat_id, ''
            us.save(update_fields=['telegram_chat_id', 'telegram_link_code'])
            reply = f'Connected to {us.user.username}. Try /today, /water 250 or /help.'
        else:
            reply = 'Open Calorio > Connections and press "Connect Telegram" to get a personal link.'
        tg_send(chat_id, reply)
        return reply

    us = UserSettings.objects.filter(telegram_chat_id=chat_id).select_related('user').first()
    if not us:
        reply = 'This chat is not linked to a Calorio account. Use the link on the Connections page.'
    elif cmd == '/today':
        reply = day_summary_text(us.user)
    elif cmd == '/water':
        try:
            ml = int(arg or 250)
            if not 1 <= ml <= 5000:
                raise ValueError
        except ValueError:
            reply = 'Usage: /water 250 (millilitres, 1-5000)'
        else:
            log, _ = WaterLog.objects.get_or_create(user=us.user, date=timezone.localdate())
            log.amount_ml = min(log.amount_ml + ml, 20000)
            log.save(update_fields=['amount_ml'])
            reply = f'Added {ml} ml. Total today: {log.amount_ml} ml.'
    elif cmd == '/stop':
        us.reminders_enabled = False
        us.save(update_fields=['reminders_enabled'])
        reply = 'Reminders turned off. Re-enable them on the Connections page.'
    else:
        reply = 'Commands: /today (summary), /water 250 (log water), /stop (turn off reminders).'
    tg_send(chat_id, reply)
    return reply


def due_reminder_key(us, now=None, window_minutes=15):
    """Return a key like '2026-10-19 13:00' if a reminder slot is due and has not been sent, else None."""
    now = timezone.localtime(now or timezone.now())
    for part in us.reminder_times.split(','):
        part = part.strip()
        try:
            hh, mm = part.split(':')
            slot = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except ValueError:
            continue
        if slot <= now < slot + timedelta(minutes=window_minutes):
            key = f'{now.date()} {int(hh):02d}:{int(mm):02d}'
            if key != us.last_reminder_key:
                return key
    return None
