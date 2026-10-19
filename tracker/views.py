from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .foodcategory import GROUPS
from .forms import ActivityForm, FoodForm, GoalForm, MealForm, MealHeaderForm, SignUpForm
from .models import ActivityEntry, DailyGoal, FavoriteFood, Food, MealEntry, WaterLog, WeightEntry
from .services import best_streak, find_food_image, logging_streak

PAGE_SIZE = 20


def _parse_date(value, default=None):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default


def _querystring(**params):
    """Filter params (without page) as a prefix for pagination links."""
    clean = {k: v for k, v in params.items() if v}
    return urlencode(clean) + '&' if clean else ''


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tracker/landing.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        DailyGoal.objects.get_or_create(user=user)
        login(request, user)
        messages.success(request, f'Welcome to Calorio, {user.username}')
        return redirect('dashboard')
    return render(request, 'registration/signup.html', {'form': form})


def _pct(value, target):
    return min(round(value / target * 100), 100) if target else 0


@login_required
def dashboard(request):
    today = timezone.localdate()
    day = _parse_date(request.GET.get('date'), today)
    if day > today:
        day = today
    meals = MealEntry.objects.filter(user=request.user, date=day).select_related('food').order_by('id')
    activity = ActivityEntry.objects.filter(user=request.user, date=day).first()

    total_calories = round(sum(m.total_calories() for m in meals), 1)
    total_protein = round(sum(m.total_protein() for m in meals), 1)
    total_carbs = round(sum(m.total_carbs() for m in meals), 1)
    total_fat = round(sum(m.total_fat() for m in meals), 1)

    goal, _ = DailyGoal.objects.get_or_create(user=request.user)
    steps = activity.steps if activity else 0
    water = WaterLog.objects.filter(user=request.user, date=day).first()
    water_ml = water.amount_ml if water else 0
    latest_weight = WeightEntry.objects.filter(user=request.user, date__lte=day).first()

    context = {
        'water_ml': water_ml,
        'water_pct': _pct(water_ml, goal.target_water_ml),
        'latest_weight': latest_weight,
        'streak': logging_streak(request.user),
        'best_streak': best_streak(request.user),
        'day': day,
        'is_today': day == today,
        'prev_day': day - timedelta(days=1),
        'next_day': day + timedelta(days=1) if day < today else None,
        'meals': meals,
        'activity': activity,
        'total_calories': total_calories,
        'total_protein': total_protein,
        'total_carbs': total_carbs,
        'total_fat': total_fat,
        'net_calories': round(total_calories - (activity.calories_burned if activity else 0), 1),
        'goal': goal,
        'cal_pct': _pct(total_calories, goal.target_calories),
        'protein_pct': _pct(total_protein, goal.target_protein),
        'steps_pct': _pct(steps, goal.target_steps),
    }
    return render(request, 'tracker/dashboard.html', context)


# ---------------------------------------------------------------- meals

@login_required
def meal_list(request):
    qs = MealEntry.objects.filter(user=request.user).select_related('food').order_by('-date', '-id')
    meal_type = request.GET.get('type', '')
    date_from = _parse_date(request.GET.get('from'))
    date_to = _parse_date(request.GET.get('to'))
    if meal_type in dict(MealEntry.MEAL_TYPES):
        qs = qs.filter(meal_type=meal_type)
    else:
        meal_type = ''
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    new_ids = {int(x) for x in request.GET.get('new', '').split(',') if x.strip().isdigit()}
    return render(request, 'tracker/meals.html', {
        'meals': page, 'page': page, 'new_ids': new_ids,
        'meal_types': MealEntry.MEAL_TYPES, 'f_type': meal_type,
        'f_from': date_from.isoformat() if date_from else '',
        'f_to': date_to.isoformat() if date_to else '',
        'extra_qs': _querystring(type=meal_type, **{'from': date_from, 'to': date_to}),
        'filtered': bool(meal_type or date_from or date_to),
    })


BUILDER_GROUPS = GROUPS + [('other', 'Other', 'Vegetables, drinks, sauces, anything else')]
MAX_ROWS_PER_GROUP = 12


def _parse_builder_rows(post, foods_by_id):
    """Read the posted rows for every group. Returns (rows_by_group, valid_items)."""
    rows, items = {}, []
    for key, _, _ in BUILDER_GROUPS:
        foods, qtys = post.getlist(f'{key}_food'), post.getlist(f'{key}_qty')
        rows[key] = []
        for i in range(min(max(len(foods), len(qtys)), MAX_ROWS_PER_GROUP)):
            fid = (foods[i] if i < len(foods) else '').strip()
            raw = (qtys[i] if i < len(qtys) else '').strip()
            if not fid and not raw:
                continue                                     # untouched blank row
            row = {'food': fid, 'qty': raw, 'error': ''}
            food = foods_by_id.get(fid)
            qty = None
            if not food:
                row['error'] = 'Choose a food from the list.'
            else:
                try:
                    qty = float(raw)
                except ValueError:
                    row['error'] = 'Enter the amount in grams.'
                else:
                    if not 0 < qty <= 5000:
                        row['error'] = 'Grams must be between 0.1 and 5000.'
            if not row['error']:
                items.append((food, round(qty, 1)))
            rows[key].append(row)
    return rows, items


@login_required
def add_meal(request):
    foods = list(Food.objects.visible_to(request.user).order_by('name'))
    foods_by_id = {str(f.id): f for f in foods}
    header = MealHeaderForm(request.POST or None, initial={'meal_type': request.GET.get('type', 'lunch')})
    rows = {k: [] for k, _, _ in BUILDER_GROUPS}
    error = ''

    if request.method == 'POST':
        rows, items = _parse_builder_rows(request.POST, foods_by_id)
        has_row_errors = any(r['error'] for rs in rows.values() for r in rs)
        if header.is_valid() and items and not has_row_errors:
            with transaction.atomic():
                created = [MealEntry.objects.create(
                    user=request.user, food=food, quantity_grams=qty,
                    meal_type=header.cleaned_data['meal_type'], date=header.cleaned_data['date']) for food, qty in items]
            messages.success(request, 'Meal added' if len(created) == 1 else f'Meal added ({len(created)} foods)')
            return redirect(f"{reverse('meal_list')}?new={','.join(str(m.id) for m in created)}")
        if not items and not has_row_errors:
            error = 'Add at least one food with an amount in grams.'
    else:
        # prefill from ?food=ID&qty=GRAMS (favourites, saved recipes, "add new food" return trip)
        pre = foods_by_id.get(request.GET.get('food', ''))
        if pre:
            rows[pre.category if pre.category in rows else 'other'].append(
                {'food': str(pre.id), 'qty': request.GET.get('qty', ''), 'error': ''})

    quick = [dict(food_payload(q['food']), favorite=q['favorite']) for q in _quick_foods(request.user, limit=16)]
    return render(request, 'tracker/meal_builder.html', {
        'header': header, 'error': error,
        'groups': [{'key': k, 'label': label, 'hint': hint} for k, label, hint in BUILDER_GROUPS],
        'rows': rows, 'food_data': [food_payload(f) for f in foods], 'quick': quick,
        'new_food_url': reverse('add_food'), 'has_foods': bool(foods),
    })


@login_required
def edit_meal(request, pk):
    meal = get_object_or_404(MealEntry, pk=pk, user=request.user)
    form = MealForm(request.POST or None, instance=meal, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Meal updated')
        return redirect(f"{reverse('meal_list')}?new={meal.id}")
    return render(request, 'tracker/form_page.html', {
        'title': 'Edit Meal', 'eyebrow': 'Update Entry', 'crumb': 'Edit Meal', 'form': form,
        'submit': 'Save Changes', 'cancel_url': reverse('meal_list'),
        'food_combo': True, 'new_food_url': reverse('add_food'),
        'food_data': [food_payload(f) for f in Food.objects.visible_to(request.user).order_by('name')],
    })


@login_required
def delete_meal(request, pk):
    meal = get_object_or_404(MealEntry, pk=pk, user=request.user)
    if request.method == 'POST':
        meal.delete()
        messages.success(request, 'Meal deleted')
        return redirect('meal_list')
    return render(request, 'tracker/confirm_delete.html', {
        'title': 'Delete Meal', 'crumb': 'Delete Meal',
        'object_label': f'{meal.food.name} ({meal.quantity_grams:g} g) on {meal.date}',
        'cancel_url': reverse('meal_list'),
    })


# ------------------------------------------------------------- activity

@login_required
def activity_list(request):
    qs = ActivityEntry.objects.filter(user=request.user).order_by('-date', '-id')
    date_from = _parse_date(request.GET.get('from'))
    date_to = _parse_date(request.GET.get('to'))
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'tracker/activity_list.html', {
        'activities': page, 'page': page,
        'f_from': date_from.isoformat() if date_from else '',
        'f_to': date_to.isoformat() if date_to else '',
        'extra_qs': _querystring(**{'from': date_from, 'to': date_to}),
        'filtered': bool(date_from or date_to),
    })


@login_required
def add_activity(request):
    form = ActivityForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        existing = ActivityEntry.objects.filter(user=request.user, date=data['date']).first()
        if existing:
            # one row per day: merge into the existing entry instead of creating a duplicate
            existing.steps += data['steps']
            existing.calories_burned += data['calories_burned']
            if data['activity_type']:
                existing.activity_type = data['activity_type']
            existing.save()
            entry = existing
            messages.success(request, f"Added to your existing entry for {data['date']}")
        else:
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, 'Activity added')
        return redirect(f"{reverse('activity_list')}?new={entry.id}")
    return render(request, 'tracker/form_page.html', {
        'title': 'Add Activity', 'eyebrow': 'New Entry', 'crumb': 'Add Activity', 'form': form,
        'submit': 'Add Activity', 'cancel_url': reverse('activity_list'),
    })


@login_required
def edit_activity(request, pk):
    entry = get_object_or_404(ActivityEntry, pk=pk, user=request.user)
    form = ActivityForm(request.POST or None, instance=entry)
    if request.method == 'POST' and form.is_valid():
        clash = ActivityEntry.objects.filter(user=request.user, date=form.cleaned_data['date']).exclude(pk=entry.pk)
        if clash.exists():
            form.add_error('date', 'You already have an activity entry for this date. Edit that one instead.')
        else:
            form.save()
            messages.success(request, 'Activity updated')
            return redirect(f"{reverse('activity_list')}?new={entry.id}")
    return render(request, 'tracker/form_page.html', {
        'title': 'Edit Activity', 'eyebrow': 'Update Entry', 'crumb': 'Edit Activity', 'form': form,
        'submit': 'Save Changes', 'cancel_url': reverse('activity_list'),
    })


@login_required
def delete_activity(request, pk):
    entry = get_object_or_404(ActivityEntry, pk=pk, user=request.user)
    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Activity deleted')
        return redirect('activity_list')
    return render(request, 'tracker/confirm_delete.html', {
        'title': 'Delete Activity', 'crumb': 'Delete Activity',
        'object_label': f'{entry.steps} steps on {entry.date}',
        'cancel_url': reverse('activity_list'),
    })


# ---------------------------------------------------------------- foods

def food_payload(food):
    return {'id': food.id, 'name': food.name, 'calories': food.calories, 'protein': food.protein, 'carbs': food.carbs,
            'fat': food.fat, 'image': food.image_url, 'emoji': food.emoji,
            'category': food.category or 'other'}


def _can_modify_food(user, food):
    """Staff may change any food; users may change only the custom foods they own."""
    return user.is_staff or (food.owner_id is not None and food.owner_id == user.id)


def _quick_foods(user, limit=8):
    """Favourites first, then recently logged foods, for one-tap logging."""
    fav = list(Food.objects.filter(favorited_by__user=user).order_by('name')[:limit])
    seen = {f.id for f in fav}
    recent = []
    for fid in MealEntry.objects.filter(user=user).order_by('-date', '-id').values_list('food_id', flat=True)[:60]:
        if fid not in seen:
            seen.add(fid)
            recent.append(fid)
        if len(fav) + len(recent) >= limit:
            break
    foods = {f.id: f for f in Food.objects.filter(id__in=recent)}
    return [{'food': f, 'favorite': True} for f in fav] + \
           [{'food': foods[i], 'favorite': False} for i in recent if i in foods]


@login_required
def food_list(request):
    q = request.GET.get('q', '').strip()
    scope = request.GET.get('scope', '')
    qs = Food.objects.visible_to(request.user).order_by('name')
    if q:
        qs = qs.filter(Q(name__icontains=q))
    if scope == 'mine':
        qs = qs.filter(owner=request.user)
    elif scope == 'favorites':
        qs = qs.filter(favorited_by__user=request.user)
    else:
        scope = ''
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    favorite_ids = set(FavoriteFood.objects.filter(user=request.user, food__in=list(page)).values_list('food_id', flat=True))
    return render(request, 'tracker/food_list.html', {
        'foods': page, 'page': page, 'q': q, 'scope': scope, 'favorite_ids': favorite_ids,
        'extra_qs': _querystring(q=q, scope=scope),
    })


@login_required
def add_food(request):
    prefill = ('name', 'calories', 'protein', 'carbs', 'fat', 'barcode', 'image_url')
    initial = {k: request.GET[k].strip()[:500] for k in prefill if request.GET.get(k)} or None
    form = FoodForm(request.POST or None, user=request.user, initial=initial)
    # when we came from the meal form, return there with the new food already selected
    back = request.POST.get('next') or request.GET.get('next') or ''
    back_ok = back in (reverse('add_meal'),)
    if request.method == 'POST' and form.is_valid():
        food = form.save(commit=False)
        food.owner = None if request.user.is_staff else request.user   # staff foods are shared with everyone
        if not food.image_url:
            food.image_url = find_food_image(food.name)               # best effort; the emoji is the fallback
        food.save()
        messages.success(request, 'Food added')
        if back_ok:
            return redirect(f"{back}?food={food.id}")
        return redirect('food_list')
    return render(request, 'tracker/form_page.html', {
        'title': 'Add a Food', 'eyebrow': 'Food Library', 'crumb': 'Add Food', 'form': form,
        'submit': 'Add Food', 'cancel_url': back if back_ok else reverse('food_list'), 'lookup': True,
        'next': back if back_ok else '',
    })


@login_required
def edit_food(request, pk):
    food = get_object_or_404(Food.objects.visible_to(request.user), pk=pk)
    if not _can_modify_food(request.user, food):
        messages.error(request, 'You can only change foods you created.')
        return redirect('food_list')
    form = FoodForm(request.POST or None, instance=food, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Food updated')
        return redirect('food_list')
    return render(request, 'tracker/form_page.html', {
        'title': 'Edit Food', 'eyebrow': 'Food Library', 'crumb': 'Edit Food', 'form': form,
        'submit': 'Save Changes', 'cancel_url': reverse('food_list'),
    })


@login_required
def delete_food(request, pk):
    food = get_object_or_404(Food.objects.visible_to(request.user), pk=pk)
    if not _can_modify_food(request.user, food):
        messages.error(request, 'You can only delete foods you created.')
        return redirect('food_list')
    if request.method == 'POST':
        food.delete()
        messages.success(request, 'Food deleted')
        return redirect('food_list')
    used = MealEntry.objects.filter(food=food).count()
    return render(request, 'tracker/confirm_delete.html', {
        'title': 'Delete Food', 'crumb': 'Delete Food', 'object_label': food.name,
        'warning': f'This will also permanently delete {used} logged meal(s) that use this food.' if used else '',
        'cancel_url': reverse('food_list'),
    })


@login_required
def toggle_favorite(request, pk):
    if request.method != 'POST':
        return redirect('food_list')
    food = get_object_or_404(Food.objects.visible_to(request.user), pk=pk)
    fav, created = FavoriteFood.objects.get_or_create(user=request.user, food=food)
    if not created:
        fav.delete()
    nxt = request.POST.get('next', '')
    if not nxt.startswith('/') or nxt.startswith('//'):
        nxt = reverse('food_list')
    return redirect(nxt)


# ---------------------------------------------------------------- goals

@login_required
def goals(request):
    goal, _ = DailyGoal.objects.get_or_create(user=request.user)
    form = GoalForm(request.POST or None, instance=goal)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Goals updated')
        return redirect('dashboard')
    return render(request, 'tracker/form_page.html', {
        'title': 'Daily Goals', 'eyebrow': 'Targets', 'crumb': 'Goals', 'form': form,
        'submit': 'Save Goals', 'cancel_url': reverse('dashboard'),
    })


# ------------------------------------------------------------ analytics

@login_required
def analytics(request):
    try:
        days = int(request.GET.get('days', 7))
    except ValueError:
        days = 7
    if days not in (7, 30, 90):
        days = 7

    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    per_day = {start + timedelta(days=i): {'cal': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0, 'steps': 0, 'burned': 0.0}
               for i in range(days)}

    meals = MealEntry.objects.filter(user=request.user, date__range=(start, end)).select_related('food')
    for m in meals:
        d = per_day[m.date]
        d['cal'] += m.total_calories()
        d['protein'] += m.total_protein()
        d['carbs'] += m.total_carbs()
        d['fat'] += m.total_fat()
    for a in ActivityEntry.objects.filter(user=request.user, date__range=(start, end)):
        d = per_day[a.date]
        d['steps'] += a.steps
        d['burned'] += a.calories_burned

    goal, _ = DailyGoal.objects.get_or_create(user=request.user)
    max_cal = max((d['cal'] for d in per_day.values()), default=0) or 1
    rows = []
    for day, d in per_day.items():
        rows.append({
            'date': day,
            'label': day.strftime('%a') if days == 7 else day.strftime('%d'),
            'cal': round(d['cal']),
            'height': max(round(d['cal'] / max_cal * 100), 3) if d['cal'] else 0,
            'over': d['cal'] > goal.target_calories,
        })

    logged = [d for d in per_day.values() if d['cal'] > 0]
    n = len(logged)
    tot = lambda key: sum(d[key] for d in per_day.values())  # noqa: E731
    p_kcal, c_kcal, f_kcal = tot('protein') * 4, tot('carbs') * 4, tot('fat') * 9
    macro_total = p_kcal + c_kcal + f_kcal

    def share(v):
        return round(v / macro_total * 100) if macro_total else 0

    context = {
        'days': days,
        'rows': rows,
        'show_labels': days <= 30,
        'days_logged': n,
        'avg_calories': round(tot('cal') / n) if n else 0,
        'avg_protein': round(tot('protein') / n, 1) if n else 0,
        'avg_steps': round(tot('steps') / days),
        'total_burned': round(tot('burned')),
        'on_target': sum(1 for d in logged if d['cal'] <= goal.target_calories),
        'best_steps': max((d['steps'] for d in per_day.values()), default=0),
        'protein_share': share(p_kcal),
        'carbs_share': share(c_kcal),
        'fat_share': share(f_kcal),
        'goal': goal,
        'range_start': start,
        'range_end': end,
    }
    return render(request, 'tracker/analytics.html', context)
