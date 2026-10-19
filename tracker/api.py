"""Small JSON API for a future mobile / SPA client.

Authentication:  Authorization: Token <key>   (create the key under Account > API access)
Logged-in browser sessions may use read-only (GET) endpoints.
"""
import json
from datetime import datetime, timedelta
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .forms import ActivityForm, MealForm, WaterForm, WeightForm
from .models import ActivityEntry, ApiToken, DailyGoal, Food, MealEntry, WaterLog, WeightEntry


def api_view(methods):
    def decorator(fn):
        @csrf_exempt
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                resp = JsonResponse({'error': 'method_not_allowed'}, status=405)
                resp['Allow'] = ', '.join(methods)
                return resp
            user = None
            header = request.headers.get('Authorization', '')
            if header.startswith('Token '):
                token = ApiToken.objects.select_related('user').filter(key=header[6:].strip()).first()
                if token and token.user.is_active:
                    user = token.user
            elif request.user.is_authenticated and request.method == 'GET':
                user = request.user          # session auth is read-only (no CSRF-exempt writes)
            if user is None:
                return JsonResponse({'error': 'authentication_required'}, status=401)
            request.api_user = user
            return fn(request, *args, **kwargs)
        return wrapper
    return decorator


def _body(request):
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _errors(form):
    return JsonResponse({'error': 'validation_failed', 'fields': {k: list(v) for k, v in form.errors.items()}}, status=400)


def _date(value, default):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default


def _meal(m):
    return {'id': m.id, 'date': m.date.isoformat(), 'meal_type': m.meal_type, 'food': m.food_id, 'food_name': m.food.name,
            'quantity_grams': m.quantity_grams, 'calories': m.total_calories(), 'protein': m.total_protein(),
            'carbs': m.total_carbs(), 'fat': m.total_fat()}


def _activity(a):
    return {'id': a.id, 'date': a.date.isoformat(), 'steps': a.steps, 'calories_burned': a.calories_burned,
            'activity_type': a.activity_type}


@api_view(['GET'])
def summary(request):
    user = request.api_user
    today = timezone.localdate()
    day = min(_date(request.GET.get('date'), today), today)
    meals = list(MealEntry.objects.filter(user=user, date=day).select_related('food'))
    act = ActivityEntry.objects.filter(user=user, date=day).first()
    water = WaterLog.objects.filter(user=user, date=day).first()
    goal, _ = DailyGoal.objects.get_or_create(user=user)
    return JsonResponse({
        'date': day.isoformat(),
        'calories': round(sum(m.total_calories() for m in meals), 1),
        'protein': round(sum(m.total_protein() for m in meals), 1),
        'carbs': round(sum(m.total_carbs() for m in meals), 1),
        'fat': round(sum(m.total_fat() for m in meals), 1),
        'steps': act.steps if act else 0,
        'calories_burned': act.calories_burned if act else 0,
        'water_ml': water.amount_ml if water else 0,
        'goals': {'calories': goal.target_calories, 'protein': goal.target_protein,
                  'steps': goal.target_steps, 'water_ml': goal.target_water_ml},
    })


@api_view(['GET', 'POST'])
def meals(request):
    user = request.api_user
    if request.method == 'POST':
        data = _body(request)
        if data is None:
            return JsonResponse({'error': 'invalid_json'}, status=400)
        form = MealForm(data, user=user)
        if not form.is_valid():
            return _errors(form)
        entry = form.save(commit=False)
        entry.user = user
        entry.save()
        return JsonResponse(_meal(entry), status=201)
    qs = MealEntry.objects.filter(user=user).select_related('food').order_by('-date', '-id')
    if request.GET.get('date'):
        qs = qs.filter(date=_date(request.GET['date'], timezone.localdate()))
    limit = min(int(request.GET.get('limit', 50)) if request.GET.get('limit', '50').isdigit() else 50, 200)
    return JsonResponse({'results': [_meal(m) for m in qs[:limit]]})


@api_view(['GET', 'DELETE'])
def meal_detail(request, pk):
    meal = MealEntry.objects.filter(pk=pk, user=request.api_user).select_related('food').first()
    if not meal:
        return JsonResponse({'error': 'not_found'}, status=404)
    if request.method == 'DELETE':
        meal.delete()
        return JsonResponse({}, status=204)
    return JsonResponse(_meal(meal))


@api_view(['GET', 'POST'])
def activity(request):
    user = request.api_user
    if request.method == 'POST':
        data = _body(request)
        if data is None:
            return JsonResponse({'error': 'invalid_json'}, status=400)
        form = ActivityForm(data)
        if not form.is_valid():
            return _errors(form)
        d = form.cleaned_data
        entry = ActivityEntry.objects.filter(user=user, date=d['date']).first()
        status = 200
        if entry:    # one row per day: merge, matching the web form
            entry.steps += d['steps']
            entry.calories_burned += d['calories_burned']
            if d['activity_type']:
                entry.activity_type = d['activity_type']
            entry.save()
        else:
            entry = form.save(commit=False)
            entry.user = user
            entry.save()
            status = 201
        return JsonResponse(_activity(entry), status=status)
    qs = ActivityEntry.objects.filter(user=user).order_by('-date')[:90]
    return JsonResponse({'results': [_activity(a) for a in qs]})


@api_view(['GET', 'POST'])
def weight(request):
    user = request.api_user
    if request.method == 'POST':
        data = _body(request)
        if data is None:
            return JsonResponse({'error': 'invalid_json'}, status=400)
        form = WeightForm(data)
        if not form.is_valid():
            return _errors(form)
        entry, created = WeightEntry.objects.update_or_create(
            user=user, date=form.cleaned_data['date'], defaults={'weight_kg': form.cleaned_data['weight_kg']})
        return JsonResponse({'id': entry.id, 'date': entry.date.isoformat(), 'weight_kg': entry.weight_kg},
                            status=201 if created else 200)
    qs = WeightEntry.objects.filter(user=user).order_by('-date')[:365]
    return JsonResponse({'results': [{'id': e.id, 'date': e.date.isoformat(), 'weight_kg': e.weight_kg} for e in qs]})


@api_view(['GET', 'POST'])
def water(request):
    user = request.api_user
    today = timezone.localdate()
    if request.method == 'POST':
        data = _body(request)
        if data is None:
            return JsonResponse({'error': 'invalid_json'}, status=400)
        form = WaterForm(data)
        if not form.is_valid():
            return _errors(form)
        day = form.cleaned_data['date'] or today
        if day > today:
            return JsonResponse({'error': 'validation_failed', 'fields': {'date': ['Cannot log in the future.']}}, status=400)
        log, _ = WaterLog.objects.get_or_create(user=user, date=day)
        log.amount_ml = min(max(log.amount_ml + form.cleaned_data['amount_ml'], 0), 20000)
        log.save(update_fields=['amount_ml'])
        return JsonResponse({'date': day.isoformat(), 'amount_ml': log.amount_ml})
    day = _date(request.GET.get('date'), today)
    log = WaterLog.objects.filter(user=user, date=day).first()
    return JsonResponse({'date': day.isoformat(), 'amount_ml': log.amount_ml if log else 0})


@api_view(['GET'])
def foods(request):
    q = request.GET.get('q', '').strip()
    qs = Food.objects.visible_to(request.api_user).order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)
    return JsonResponse({'results': [
        {'id': f.id, 'name': f.name, 'calories': f.calories, 'protein': f.protein, 'carbs': f.carbs, 'fat': f.fat,
         'custom': f.owner_id is not None} for f in qs[:100]]})
