"""Business logic that does not belong in views: streaks, calorie calculator, Open Food Facts lookups."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.utils import timezone

from .models import MealEntry

OFF_BASE = 'https://world.openfoodfacts.org'
OFF_TIMEOUT = 6
OFF_HEADERS = {'User-Agent': 'Calorio/1.0 (calorie tracker)'}


# ---------------------------------------------------------------- streaks

def logging_streak(user, today=None):
    """Consecutive days with at least one meal logged, ending today (or yesterday if today is still empty)."""
    today = today or timezone.localdate()
    days = set(MealEntry.objects.filter(user=user, date__gte=today - timedelta(days=400))
               .values_list('date', flat=True))
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def best_streak(user):
    days = sorted(set(MealEntry.objects.filter(user=user).values_list('date', flat=True)))
    best = run = 0
    prev = None
    for d in days:
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


# ------------------------------------------------------------ calculator

def calculate_targets(sex, age, height_cm, weight_kg, activity, goal):
    """Mifflin-St Jeor BMR scaled by activity, adjusted for the goal."""
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == 'male' else -161)
    tdee = bmr * float(activity)
    adjust = {'lose': -500, 'maintain': 0, 'gain': 300}[goal]
    floor = 1500 if sex == 'male' else 1200
    calories = max(round((tdee + adjust) / 10) * 10, floor)
    per_kg = {'lose': 2.0, 'maintain': 1.6, 'gain': 1.8}[goal]
    return {
        'bmr': round(bmr),
        'tdee': round(tdee),
        'calories': calories,
        'protein': round(weight_kg * per_kg),
        'water_ml': round(weight_kg * 35 / 50) * 50,
    }


# --------------------------------------------------------- Open Food Facts

def _get_json(url):
    req = urllib.request.Request(url, headers=OFF_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=OFF_TIMEOUT) as resp:  # noqa: S310 - fixed https host
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _num(nutriments, key):
    try:
        return round(float(nutriments.get(key) or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def _https(url):
    url = (url or '').strip()
    return url if url.startswith('https://') and len(url) <= 500 else ''


def _normalise(product):
    """Map an Open Food Facts product to our per-100g food fields; None if unusable."""
    if not product:
        return None
    n = product.get('nutriments') or {}
    name = (product.get('product_name') or '').strip()
    kcal = _num(n, 'energy-kcal_100g')
    if not kcal and n.get('energy_100g'):
        kcal = round(float(n['energy_100g']) / 4.184, 1)
    if not name or not kcal:
        return None
    brands = product.get('brands') or ''
    if isinstance(brands, list):
        brands = brands[0] if brands else ''
    brand = str(brands).split(',')[0].strip()
    return {
        'name': f'{name} ({brand})' if brand else name,
        'calories': kcal,
        'protein': _num(n, 'proteins_100g'),
        'carbs': _num(n, 'carbohydrates_100g'),
        'fat': _num(n, 'fat_100g'),
        'barcode': str(product.get('code') or ''),
        'image': _https(product.get('image_front_small_url') or product.get('image_front_url') or product.get('image_url')),
    }


def lookup_barcode(code):
    code = ''.join(ch for ch in str(code) if ch.isdigit())
    if not 8 <= len(code) <= 14:
        return []
    data = _get_json(f'{OFF_BASE}/api/v2/product/{code}.json?fields=code,product_name,brands,nutriments,image_front_small_url,image_front_url')
    if not data or data.get('status') != 1:
        return []
    item = _normalise(data.get('product'))
    return [item] if item else []


def search_foods(query, limit=8):
    """Search packaged products. Uses Open Food Facts' search service (the old cgi/search.pl endpoint now returns 503)."""
    query = (query or '').strip()
    if len(query) < 2:
        return []
    params = urllib.parse.urlencode({
        'q': query, 'page_size': 20, 'langs': 'en',
        'fields': 'code,product_name,brands,nutriments,image_front_small_url,image_front_url',
    })
    data = _get_json(f'https://search.openfoodfacts.org/search?{params}')
    results = []
    for product in (data or {}).get('hits', []) or (data or {}).get('products', []):
        item = _normalise(product)
        if item:
            results.append(item)
        if len(results) >= limit:
            break
    return results


# ------------------------------------------------------- weekly summary

def weekly_summary(user, end=None):
    """Totals and averages for the 7 days ending on `end` (default today)."""
    from .models import ActivityEntry, DailyGoal, WeightEntry
    end = end or timezone.localdate()
    start = end - timedelta(days=6)
    meals = list(MealEntry.objects.filter(user=user, date__range=(start, end)).select_related('food'))
    per_day = {}
    for m in meals:
        per_day[m.date] = per_day.get(m.date, 0) + m.total_calories()
    goal, _ = DailyGoal.objects.get_or_create(user=user)
    acts = ActivityEntry.objects.filter(user=user, date__range=(start, end))
    weights = list(WeightEntry.objects.filter(user=user, date__range=(start, end)).order_by('date'))
    logged = len(per_day)
    return {
        'start': start, 'end': end, 'days_logged': logged,
        'avg_calories': round(sum(per_day.values()) / logged) if logged else 0,
        'avg_protein': round(sum(m.total_protein() for m in meals) / logged, 1) if logged else 0,
        'on_target': sum(1 for c in per_day.values() if c <= goal.target_calories),
        'total_steps': sum(a.steps for a in acts),
        'total_burned': round(sum(a.calories_burned for a in acts)),
        'weight_change': round(weights[-1].weight_kg - weights[0].weight_kg, 1) if len(weights) >= 2 else None,
        'streak': logging_streak(user, end),
        'goal_calories': round(goal.target_calories),
    }


# ------------------------------------------------------- generic food photos

_FOODISH = ('food', 'fruit', 'vegetable', 'dish', 'meat', 'cuisine', 'dairy', 'bread', 'cereal', 'nut', 'drink',
            'beverage', 'edible', 'species', 'plant', 'cooked', 'sauce', 'snack', 'dessert', 'grain', 'legume',
            'seafood', 'fish', 'poultry', 'egg', 'cheese', 'pastry', 'soup', 'salad', 'rice', 'pasta', 'berry', 'herb')


def find_food_image(name):
    """Best-effort photo for a generic food from Wikipedia. Returns an https URL or ''."""
    title = (name or '').split('(')[0].strip()
    if len(title) < 3:
        return ''
    data = _get_json('https://en.wikipedia.org/api/rest_v1/page/summary/'
                     + urllib.parse.quote(title.replace(' ', '_'), safe='') + '?redirect=true')
    if not data or data.get('type') != 'standard':
        return ''
    blurb = f"{data.get('description') or ''} {(data.get('extract') or '')[:300]}".lower()
    if not any(k in blurb for k in _FOODISH):
        return ''                       # avoid matching an unrelated article (a band, a company, a place)
    return _https((data.get('thumbnail') or {}).get('source'))
