import logging
import re

import requests
from django.core.cache import cache
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import viewsets, permissions, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .ai import parse_meal_text, estimate_restaurant_meal
from .models import Meal, Activity, Food
from .serializers import MealSerializer, ActivitySerializer, FoodSerializer


class MealViewSet(viewsets.ModelViewSet):
    serializer_class = MealSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Meal.objects.filter(user=self.request.user).order_by('-eaten_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ActivityViewSet(viewsets.ModelViewSet):
    serializer_class = ActivitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Activity.objects.filter(user=self.request.user).order_by('-date')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        meals = Meal.objects.filter(user=request.user)

        totals = meals.filter(eaten_at__date=today).aggregate(
            calories=Sum('calories'), protein=Sum('protein')
        )
        steps = Activity.objects.filter(user=request.user, date=today).aggregate(
            steps=Sum('steps')
        )
        daily = (
            meals.annotate(day=TruncDate('eaten_at'))
            .values('day')
            .annotate(calories=Sum('calories'), protein=Sum('protein'))
            .order_by('-day')
        )

        return Response({
            'today': {
                'calories': totals['calories'] or 0,
                'protein': totals['protein'] or 0,
                'steps': steps['steps'] or 0,
            },
            'daily': list(daily),
        })


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.user == request.user


class FoodViewSet(viewsets.ModelViewSet):
    serializer_class = FoodSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        return Food.objects.filter(Q(user=None) | Q(user=self.request.user)).order_by('name')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


def clean_number(value, high=5000):
    return min(max(float(value), 0), high)


class ParseMealView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'parse'

    def post(self, request):
        text = str(request.data.get('text', '')).strip()[:300]
        if not text:
            return Response({'detail': 'Text is required.'}, status=400)

        foods = list(Food.objects.filter(Q(user=None) | Q(user=request.user)))
        try:
            data = parse_meal_text(text, foods)
        except Exception:
            logging.exception('parse-meal failed')
            return Response({'detail': 'Could not understand that. Try again.'}, status=502)

        by_id = {f.id: f for f in foods}

        items = []
        for it in data.get('items', []):
            food = by_id.get(it.get('food_id'))
            try:
                servings = float(it.get('servings', 1))
            except (TypeError, ValueError):
                continue
            if food and 0 < servings <= 20:
                items.append({'food': FoodSerializer(food).data, 'servings': servings})

        unmatched = []
        for it in data.get('unmatched', []):
            try:
                unmatched.append({
                    'name': str(it['name'])[:100],
                    'calories': round(clean_number(it['calories'])),
                    'protein': round(clean_number(it.get('protein', 0), 500), 1),
                    'carbs': round(clean_number(it.get('carbs', 0), 1000), 1),
                    'fat': round(clean_number(it.get('fat', 0), 500), 1),
                })
            except (KeyError, TypeError, ValueError):
                continue

        return Response({'items': items, 'unmatched': unmatched})


class EstimateMealView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'estimate'

    def post(self, request):
        text = str(request.data.get('text', '')).strip()[:200]
        if not text:
            return Response({'detail': 'Text is required.'}, status=400)

        try:
            data = estimate_restaurant_meal(text)
            if 'error' in data:
                return Response({'detail': 'That does not look like food.'}, status=400)

            # sort so low <= mid <= high even if the AI mixes them up
            low, mid, high = sorted([
                clean_number(data['calories_low']),
                clean_number(data['calories_mid']),
                clean_number(data['calories_high']),
            ])
            result = {
                'name': str(data['name'])[:100],
                'low': round(low),
                'mid': round(mid),
                'high': round(high),
                'protein': round(clean_number(data.get('protein', 0), 500), 1),
                'carbs': round(clean_number(data.get('carbs', 0), 1000), 1),
                'fat': round(clean_number(data.get('fat', 0), 500), 1),
                'note': str(data.get('note', ''))[:200],
            }
        except Exception:
            logging.exception('estimate-meal failed')
            return Response({'detail': 'Could not estimate that. Try again.'}, status=502)

        return Response(result)


OFF_URL = 'https://world.openfoodfacts.org/api/v2/product/{}.json'
OFF_HEADERS = {'User-Agent': 'Calorio/1.0 (learning project)'}


def to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class BarcodeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'barcode'

    def get(self, request, code):
        # digits only, so nothing odd can be put into the URL we call
        if not re.fullmatch(r'\d{8,14}', code):
            return Response({'detail': 'Invalid barcode.'}, status=400)

        cached = cache.get(f'off:{code}')
        if cached:
            return Response(cached)

        try:
            r = requests.get(
                OFF_URL.format(code),
                headers=OFF_HEADERS,
                params={'fields': 'product_name,brands,nutriments,serving_size,serving_quantity'},
                timeout=8,
            )
        except requests.RequestException:
            logging.exception('barcode lookup failed')
            return Response({'detail': 'Food database is not reachable.'}, status=502)

        if r.status_code == 404:
            return Response({'detail': 'Product not found.'}, status=404)
        if r.status_code != 200:
            return Response({'detail': 'Food database error.'}, status=502)

        data = r.json()
        product = data.get('product')
        if data.get('status') == 0 or not product:
            return Response({'detail': 'Product not found.'}, status=404)

        n = product.get('nutriments') or {}
        kcal = to_number(n.get('energy-kcal_100g'))
        if kcal is None:
            kj = to_number(n.get('energy-kj_100g'))
            kcal = kj / 4.184 if kj is not None else None
        if kcal is None:
            return Response({'detail': 'This product has no calorie data.'}, status=404)

        def macro(key):
            return round(clean_number(to_number(n.get(key)) or 0, 100), 1)

        result = {
            'code': code,
            'name': str(product.get('product_name') or 'Unknown product')[:100],
            'brand': str(product.get('brands') or '')[:100],
            'per100': {
                'calories': round(clean_number(kcal, 1000)),
                'protein': macro('proteins_100g'),
                'carbs': macro('carbohydrates_100g'),
                'fat': macro('fat_100g'),
            },
            'serving_size': str(product.get('serving_size') or '')[:50],
            'serving_grams': to_number(product.get('serving_quantity')),
        }
        cache.set(f'off:{code}', result, 60 * 60 * 24)
        return Response(result)