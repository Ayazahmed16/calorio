from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Activity, Badge, Goal, Meal

STEPS_TARGET = 8000


def current_streak(days, today):
    # if today does not count yet, the streak is still alive until the day ends
    day = today if today in days else today - timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count


def longest_streak(days):
    best = run = 0
    previous = None
    for d in sorted(days):
        run = run + 1 if previous and d - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = d
    return best


def compute_stats(user):
    goal, _ = Goal.objects.get_or_create(user=user)
    today = timezone.localdate()

    meal_rows = list(
        Meal.objects.filter(user=user)
        .annotate(day=TruncDate('eaten_at'))
        .values('day')
        .annotate(total_protein=Sum('protein'))
    )
    logged = {r['day'] for r in meal_rows}
    protein_days = (
        {r['day'] for r in meal_rows if r['total_protein'] >= goal.protein}
        if goal.protein > 0 else set()
    )

    step_rows = Activity.objects.filter(user=user).values('date').annotate(total_steps=Sum('steps'))
    steps_days = {r['date'] for r in step_rows if r['total_steps'] >= STEPS_TARGET}

    def summary(days):
        return {'current': current_streak(days, today), 'best': longest_streak(days)}

    return {
        'meals': Meal.objects.filter(user=user).count(),
        'logging': summary(logged),
        'protein': summary(protein_days),
        'steps': summary(steps_days),
    }


# code: (name, description, check function)
BADGES = {
    'first_meal': ('First bite', 'Log your first meal', lambda s: s['meals'] >= 1),
    'log_3': ('3-day logger', 'Log meals 3 days in a row', lambda s: s['logging']['best'] >= 3),
    'log_7': ('Week warrior', 'Log meals 7 days in a row', lambda s: s['logging']['best'] >= 7),
    'log_30': ('Habit master', 'Log meals 30 days in a row', lambda s: s['logging']['best'] >= 30),
    'protein_3': ('Protein starter', 'Hit your protein goal 3 days in a row', lambda s: s['protein']['best'] >= 3),
    'protein_7': ('Protein pro', 'Hit your protein goal 7 days in a row', lambda s: s['protein']['best'] >= 7),
    'steps_3': ('Step starter', f'Reach {STEPS_TARGET} steps 3 days in a row', lambda s: s['steps']['best'] >= 3),
    'steps_7': ('Step champion', f'Reach {STEPS_TARGET} steps 7 days in a row', lambda s: s['steps']['best'] >= 7),
}


def award_badges(user, stats=None):
    stats = stats or compute_stats(user)
    have = set(Badge.objects.filter(user=user).values_list('code', flat=True))
    new = []
    for code, (_, _, check) in BADGES.items():
        if code not in have and check(stats):
            Badge.objects.get_or_create(user=user, code=code)
            new.append(code)
    return new