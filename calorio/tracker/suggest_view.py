from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Food, Meal, Goal
from .serializers import FoodSerializer
from .suggestions import suggest_meals


class GoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Goal
        fields = ['calories', 'protein']
        extra_kwargs = {
            'calories': {'min_value': 500, 'max_value': 10000},
            'protein': {'min_value': 0, 'max_value': 500},
        }


class GoalView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        goal, _ = Goal.objects.get_or_create(user=request.user)
        return Response(GoalSerializer(goal).data)

    def put(self, request):
        goal, _ = Goal.objects.get_or_create(user=request.user)
        serializer = GoalSerializer(goal, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SuggestionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        goal, _ = Goal.objects.get_or_create(user=request.user)
        today = timezone.localdate()
        eaten = Meal.objects.filter(user=request.user, eaten_at__date=today).aggregate(
            calories=Sum('calories'), protein=Sum('protein')
        )
        left_cal = goal.calories - (eaten['calories'] or 0)
        left_protein = max(0, goal.protein - (eaten['protein'] or 0))

        foods = list(
            Food.objects.filter(Q(user=None) | Q(user=request.user), calories__gt=0)
            .order_by('name')[:60]
        )
        meals = suggest_meals(foods, left_cal, left_protein)

        return Response({
            'left': {'calories': left_cal, 'protein': round(left_protein, 1)},
            'suggestions': [
                {
                    'items': [
                        {'food': FoodSerializer(it['food']).data, 'servings': it['servings']}
                        for it in m['items']
                    ],
                    'calories': round(m['calories']),
                    'protein': round(m['protein'], 1),
                    'carbs': round(m['carbs'], 1),
                    'fat': round(m['fat'], 1),
                }
                for m in meals
            ],
        })