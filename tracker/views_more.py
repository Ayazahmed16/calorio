"""Weight, water, saved meals, calculator, account, CSV import/export, food lookup and PWA views."""
import csv
import io
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (ActivityForm, CalculatorForm, CsvImportForm, LogSavedMealForm, MealForm, SavedMealForm,
                    WaterForm, WeightForm)
from .models import (ActivityEntry, ApiToken, DailyGoal, Food, MealEntry, SavedMeal, SavedMealItem, WaterLog,
                     WeightEntry)
from .integrations import search_all
from .services import calculate_targets, lookup_barcode

PAGE_SIZE = 20
MAX_IMPORT_ROWS = 5000


def _safe_next(request, default):
    nxt = request.POST.get('next') or request.GET.get('next') or ''
    return nxt if nxt.startswith('/') and not nxt.startswith('//') else default


# ---------------------------------------------------------------- weight

@login_required
def weight(request):
    form = WeightForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        entry, created = WeightEntry.objects.update_or_create(
            user=request.user, date=form.cleaned_data['date'],
            defaults={'weight_kg': form.cleaned_data['weight_kg']})
        messages.success(request, 'Weight logged' if created else 'Weight updated for that day')
        return redirect('weight')

    entries = WeightEntry.objects.filter(user=request.user).order_by('-date')
    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get('page'))

    since = timezone.localdate() - timedelta(days=89)
    series = list(WeightEntry.objects.filter(user=request.user, date__gte=since).order_by('date'))
    chart = None
    if len(series) >= 2:
        lo, hi = min(e.weight_kg for e in series), max(e.weight_kg for e in series)
        span = (hi - lo) or 1
        d0, d1 = series[0].date, series[-1].date
        dspan = max((d1 - d0).days, 1)
        pts = []
        for e in series:
            x = 20 + (e.date - d0).days / dspan * 560
            y = 20 + (1 - (e.weight_kg - lo) / span) * 160
            pts.append({'x': round(x, 1), 'y': round(y, 1), 'kg': e.weight_kg, 'date': e.date})
        chart = {'points': pts, 'poly': ' '.join(f"{p['x']},{p['y']}" for p in pts), 'lo': lo, 'hi': hi}

    latest = entries.first()
    month_ago = WeightEntry.objects.filter(user=request.user, date__lte=timezone.localdate() - timedelta(days=30)).first()
    return render(request, 'tracker/weight.html', {
        'form': form, 'entries': page, 'page': page, 'chart': chart, 'latest': latest,
        'change_30d': round(latest.weight_kg - month_ago.weight_kg, 1) if latest and month_ago else None,
        'lowest': entries.order_by('weight_kg').first(),
    })


@login_required
def delete_weight(request, pk):
    entry = get_object_or_404(WeightEntry, pk=pk, user=request.user)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Weight entry deleted')
        return redirect('weight')
    return render(request, 'tracker/confirm_delete.html', {
        'title': 'Delete Weight Entry', 'crumb': 'Delete Weight',
        'object_label': f'{entry.weight_kg:g} kg on {entry.date}', 'cancel_url': reverse('weight'),
    })


# ----------------------------------------------------------------- water

@login_required
@require_POST
def add_water(request):
    form = WaterForm(request.POST)
    dest = _safe_next(request, reverse('dashboard'))
    if not form.is_valid():
        messages.error(request, 'Enter a valid water amount.')
        return redirect(dest)
    day = form.cleaned_data['date'] or timezone.localdate()
    if day > timezone.localdate():
        messages.error(request, 'You cannot log water in the future.')
        return redirect(dest)
    log, _ = WaterLog.objects.get_or_create(user=request.user, date=day)
    log.amount_ml = min(max(log.amount_ml + form.cleaned_data['amount_ml'], 0), 20000)
    log.save(update_fields=['amount_ml'])
    messages.success(request, f'Water: {log.amount_ml} ml today' if day == timezone.localdate() else f'Water: {log.amount_ml} ml on {day}')
    return redirect(dest)


# ----------------------------------------------------------- saved meals

@login_required
def saved_meals(request):
    form = SavedMealForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            saved = SavedMeal.objects.create(user=request.user, name=d['name'])
            totals = {}
            for m in MealEntry.objects.filter(user=request.user, date=d['date'], meal_type=d['meal_type']):
                totals[m.food_id] = totals.get(m.food_id, 0) + m.quantity_grams
            SavedMealItem.objects.bulk_create(
                [SavedMealItem(saved_meal=saved, food_id=fid, quantity_grams=q) for fid, q in totals.items()])
        messages.success(request, f'Saved "{saved.name}"')
        return redirect('saved_meals')
    items = SavedMeal.objects.filter(user=request.user).prefetch_related('items__food')
    rows = []
    for s in items:
        rows.append({'obj': s, 'items': list(s.items.all()), 'totals': s.totals()})
    return render(request, 'tracker/saved_meals.html', {
        'rows': rows, 'form': form, 'meal_types': MealEntry.MEAL_TYPES, 'today': timezone.localdate(),
    })


@login_required
@require_POST
def log_saved_meal(request, pk):
    saved = get_object_or_404(SavedMeal, pk=pk, user=request.user)
    form = LogSavedMealForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Choose a valid meal type and date.')
        return redirect('saved_meals')
    d = form.cleaned_data
    items = list(saved.items.select_related('food'))
    # a food can disappear from a user's library; only log what still exists
    MealEntry.objects.bulk_create([
        MealEntry(user=request.user, food=i.food, quantity_grams=i.quantity_grams, meal_type=d['meal_type'], date=d['date'])
        for i in items])
    messages.success(request, f'Logged "{saved.name}" ({len(items)} item{"s" if len(items) != 1 else ""})')
    return redirect(f"{reverse('dashboard')}?date={d['date']}")


@login_required
def delete_saved_meal(request, pk):
    saved = get_object_or_404(SavedMeal, pk=pk, user=request.user)
    if request.method == 'POST':
        saved.delete()
        messages.success(request, 'Saved meal deleted')
        return redirect('saved_meals')
    return render(request, 'tracker/confirm_delete.html', {
        'title': 'Delete Saved Meal', 'crumb': 'Delete Saved Meal', 'object_label': saved.name,
        'cancel_url': reverse('saved_meals'),
    })


# ------------------------------------------------------------ calculator

@login_required
def calculator(request):
    form = CalculatorForm(request.POST or None, initial={'weight_kg': _latest_weight(request.user)})
    result = None
    if request.method == 'POST' and form.is_valid():
        result = calculate_targets(**form.cleaned_data)
        if request.POST.get('apply'):
            goal, _ = DailyGoal.objects.get_or_create(user=request.user)
            goal.target_calories = result['calories']
            goal.target_protein = result['protein']
            goal.target_water_ml = min(max(result['water_ml'], 500), 10000)
            goal.save()
            messages.success(request, 'Your daily goals were updated')
            return redirect('goals')
    return render(request, 'tracker/calculator.html', {'form': form, 'result': result})


def _latest_weight(user):
    w = WeightEntry.objects.filter(user=user).first()
    return w.weight_kg if w else None


# --------------------------------------------------------------- account

@login_required
def account(request):
    token, _ = ApiToken.objects.get_or_create(user=request.user)
    return render(request, 'tracker/account.html', {
        'token': token, 'import_form': CsvImportForm(),
        'base_url': request.build_absolute_uri('/api/v1/'),
    })


@login_required
@require_POST
def regenerate_token(request):
    token, _ = ApiToken.objects.get_or_create(user=request.user)
    token.regenerate()
    messages.success(request, 'New API token generated. The old one no longer works.')
    return redirect('account')


# ------------------------------------------------------------ CSV export

def _cell(value):
    """Neutralise spreadsheet formulas in user-controlled text."""
    s = str(value)
    return "'" + s if s[:1] in ('=', '+', '-', '@', '\t', '\r') else s


@login_required
def export_csv(request, kind):
    if kind not in ('meals', 'activity', 'weight'):
        return redirect('account')
    resp = HttpResponse(content_type='text/csv; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="calorio-{kind}-{timezone.localdate()}.csv"'
    w = csv.writer(resp)
    if kind == 'meals':
        w.writerow(['date', 'meal_type', 'food', 'quantity_grams', 'calories', 'protein', 'carbs', 'fat'])
        for m in MealEntry.objects.filter(user=request.user).select_related('food').order_by('date', 'id'):
            w.writerow([m.date, m.meal_type, _cell(m.food.name), m.quantity_grams, m.total_calories(),
                        m.total_protein(), m.total_carbs(), m.total_fat()])
    elif kind == 'activity':
        w.writerow(['date', 'steps', 'calories_burned', 'activity_type'])
        for a in ActivityEntry.objects.filter(user=request.user).order_by('date'):
            w.writerow([a.date, a.steps, a.calories_burned, _cell(a.activity_type)])
    else:
        w.writerow(['date', 'weight_kg'])
        for e in WeightEntry.objects.filter(user=request.user).order_by('date'):
            w.writerow([e.date, e.weight_kg])
    return resp


# ------------------------------------------------------------ CSV import

def _rows(upload):
    text = upload.read().decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [(h or '').strip().lower() for h in (reader.fieldnames or [])]
    return reader


@login_required
@require_POST
def import_csv(request):
    form = CsvImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, next(iter(sum(form.errors.values(), [])), 'Invalid upload.'))
        return redirect('account')
    kind = form.cleaned_data['kind']
    reader = _rows(form.cleaned_data['file'])
    required = {'meals': {'date', 'meal_type', 'food', 'quantity_grams'},
                'activity': {'date', 'steps', 'calories_burned'},
                'weight': {'date', 'weight_kg'}}[kind]
    missing = required - set(reader.fieldnames or [])
    if missing:
        messages.error(request, 'Missing column(s): ' + ', '.join(sorted(missing)))
        return redirect('account')

    visible = {f.name.lower(): f.id for f in Food.objects.visible_to(request.user)}
    errors, created = [], 0
    try:
        with transaction.atomic():
            for n, row in enumerate(reader, start=2):
                if n - 1 > MAX_IMPORT_ROWS:
                    errors.append(f'Too many rows (limit {MAX_IMPORT_ROWS}).')
                    break
                row = {k: (v or '').strip() for k, v in row.items() if k}
                if kind == 'meals':
                    fid = visible.get(row.get('food', '').lower())
                    if not fid:
                        errors.append(f'Row {n}: unknown food "{row.get("food", "")}"')
                        continue
                    f = MealForm({'food': fid, 'quantity_grams': row['quantity_grams'],
                                  'meal_type': row['meal_type'].lower(), 'date': row['date']}, user=request.user)
                    if f.is_valid():
                        e = f.save(commit=False)
                        e.user = request.user
                        e.save()
                        created += 1
                    else:
                        errors.append(f'Row {n}: ' + '; '.join(sum(f.errors.values(), [])))
                elif kind == 'activity':
                    f = ActivityForm({'steps': row['steps'], 'calories_burned': row['calories_burned'],
                                      'activity_type': row.get('activity_type', ''), 'date': row['date']})
                    if f.is_valid():
                        d = f.cleaned_data
                        ActivityEntry.objects.update_or_create(
                            user=request.user, date=d['date'],
                            defaults={'steps': d['steps'], 'calories_burned': d['calories_burned'],
                                      'activity_type': d['activity_type']})
                        created += 1
                    else:
                        errors.append(f'Row {n}: ' + '; '.join(sum(f.errors.values(), [])))
                else:
                    f = WeightForm({'date': row['date'], 'weight_kg': row['weight_kg']})
                    if f.is_valid():
                        WeightEntry.objects.update_or_create(
                            user=request.user, date=f.cleaned_data['date'],
                            defaults={'weight_kg': f.cleaned_data['weight_kg']})
                        created += 1
                    else:
                        errors.append(f'Row {n}: ' + '; '.join(sum(f.errors.values(), [])))
                if len(errors) >= 20:
                    break
            if errors:
                raise ValueError('rollback')
    except ValueError:
        shown = errors[:5]
        more = f' (+{len(errors) - 5} more)' if len(errors) > 5 else ''
        messages.error(request, 'Nothing was imported. ' + ' | '.join(shown) + more)
        return redirect('account')
    messages.success(request, f'Imported {created} {kind} row{"s" if created != 1 else ""}')
    return redirect('account')


# ----------------------------------------------------------- food lookup

@login_required
def food_lookup(request):
    barcode = request.GET.get('barcode', '').strip()
    q = request.GET.get('q', '').strip()[:80]
    if barcode:
        results = lookup_barcode(barcode)
    else:
        results = search_all(q)          # USDA generic foods + Open Food Facts products
    for r in results:
        r.setdefault('source', 'Open Food Facts')
    return JsonResponse({'results': results})


# ------------------------------------------------------------------- PWA

def manifest(request):
    data = {
        'name': 'Calorio', 'short_name': 'Calorio', 'description': 'Nutrition and activity tracker',
        'start_url': '/dashboard/', 'scope': '/', 'display': 'standalone',
        'background_color': '#0a1214', 'theme_color': '#0a1214',
        'icons': [
            {'src': '/static/tracker/icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
            {'src': '/static/tracker/icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
            {'src': '/static/tracker/icons/icon-maskable-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    return JsonResponse(data, content_type='application/manifest+json')


def service_worker(request):
    resp = HttpResponse(render_to_string('sw.js'), content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    resp['Cache-Control'] = 'no-cache'
    return resp


def offline(request):
    return render(request, 'offline.html')
