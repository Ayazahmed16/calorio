import logging

from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .ai import suggest_recipes
from .models import Goal, Meal
from .suggestions import score_meal


def to_number(value, high):
    try:
        return min(max(float(value), 0), high)
    except (TypeError, ValueError):
        return 0


def to_list(value, max_items, max_len):
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:max_len] for v in value[:max_items] if str(v).strip()]


class RecipeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'recipes'

    def post(self, request):
        items = [
            i.strip()[:40]
            for i in str(request.data.get('ingredients', '')).split(',')
            if i.strip()
        ][:15]
        if not items:
            return Response({'detail': 'Add at least one ingredient.'}, status=400)

        goal, _ = Goal.objects.get_or_create(user=request.user)
        eaten = Meal.objects.filter(
            user=request.user, eaten_at__date=timezone.localdate()
        ).aggregate(calories=Sum('calories'), protein=Sum('protein'))
        left_cal = goal.calories - (eaten['calories'] or 0)
        left_protein = max(0, goal.protein - (eaten['protein'] or 0))
        left = {'calories': left_cal, 'protein': round(left_protein, 1)}

        if left_cal <= 0:
            return Response({'left': left, 'recipes': []})

        try:
            data = suggest_recipes(items, left_cal, left_protein)
        except Exception:
            logging.exception('recipes failed')
            return Response({'detail': 'Could not make recipes. Try again.'}, status=502)

        raw_recipes = data.get('recipes', []) if isinstance(data, dict) else []

        recipes = []
        for r in raw_recipes:
            if not isinstance(r, dict):
                continue
            name = str(r.get('name', '')).strip()[:100]
            calories = to_number(r.get('calories'), 5000)
            protein = to_number(r.get('protein'), 500)
            if not name or calories < 50 or calories > left_cal:
                continue  # unusable, or over your budget
            recipes.append({
                'name': name,
                'minutes': round(to_number(r.get('minutes'), 240)),
                'ingredients_used': to_list(r.get('ingredients_used'), 12, 50),
                'extra_needed': to_list(r.get('extra_needed'), 12, 50),
                'calories': round(calories),
                'protein': round(protein, 1),
                'carbs': round(to_number(r.get('carbs'), 1000), 1),
                'fat': round(to_number(r.get('fat'), 500), 1),
                'steps': to_list(r.get('steps'), 8, 200),
                'score': score_meal(calories, protein, left_cal, left_protein),
            })

        recipes.sort(key=lambda r: r['score'])  # lower score = better fit
        for r in recipes:
            del r['score']

        return Response({'left': left, 'recipes': recipes[:3]})