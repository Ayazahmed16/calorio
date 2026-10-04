from unittest.mock import patch
from django.core.cache import cache
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from .models import Meal, Food


class MealAPITests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user('a', password='pass12345')
        self.user_b = User.objects.create_user('b', password='pass12345')
        self.client = APIClient()

    def test_anonymous_user_is_blocked(self):
        response = self.client.get('/api/meals/')
        self.assertIn(response.status_code, [401, 403])

    def test_user_can_create_meal(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/meals/', {'name': 'Rice', 'calories': 300, 'protein': 6})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Meal.objects.filter(user=self.user_a).count(), 1)

    def test_user_sees_only_own_meals(self):
        Meal.objects.create(user=self.user_a, name='A meal', calories=100)
        Meal.objects.create(user=self.user_b, name='B meal', calories=200)

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/meals/')

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'A meal')

    def test_user_cannot_delete_other_users_meal(self):
        meal = Meal.objects.create(user=self.user_b, name='B meal', calories=200)

        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/meals/{meal.id}/')

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Meal.objects.filter(id=meal.id).exists())

    def test_summary_totals_today(self):
        Meal.objects.create(user=self.user_a, name='M1', calories=300, protein=10)
        Meal.objects.create(user=self.user_a, name='M2', calories=200, protein=5)
        Meal.objects.create(user=self.user_b, name='Other', calories=999, protein=99)

        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/summary/')

        self.assertEqual(response.data['today']['calories'], 500)
        self.assertEqual(response.data['today']['protein'], 15)

    def test_log_food_calculates_macros(self):
        food = Food.objects.create(name='Roti', calories=120, protein=3.5, carbs=20, fat=3)
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/meals/', {'food': food.id, 'servings': 2, 'meal_type': 'lunch'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['calories'], 240)
        self.assertEqual(response.data['protein'], 7.0)

    def test_cannot_delete_shared_food(self):
        food = Food.objects.create(name='Roti', calories=120)
        self.client.force_authenticate(user=self.user_a)
        response = self.client.delete(f'/api/foods/{food.id}/')
        self.assertEqual(response.status_code, 403)

    @patch('tracker.api_views.parse_meal_text')
    def test_parse_meal_drops_invalid_ids(self, mock_parse):
        food = Food.objects.create(name='Roti', calories=120)
        mock_parse.return_value = {
            'items': [{'food_id': food.id, 'servings': 2}, {'food_id': 9999, 'servings': 1}],
            'unmatched': [],
        }
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/parse-meal/', {'text': '2 rotis'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['items']), 1)

    @patch('tracker.api_views.estimate_restaurant_meal')
    def test_estimate_sorts_range(self, mock_estimate):
        mock_estimate.return_value = {
            'name': 'Biryani', 'calories_low': 1000, 'calories_mid': 700,
            'calories_high': 850, 'protein': 30, 'carbs': 90, 'fat': 30, 'note': 'x',
        }
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post('/api/estimate-meal/', {'text': 'biryani'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.data['low'], response.data['mid'], response.data['high']),
            (700, 850, 1000),
        )
    @patch('tracker.api_views.requests.get')
    def test_barcode_lookup(self, mock_get):
        cache.clear()
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'status': 1,
            'product': {
                'product_name': 'Spread',
                'brands': 'X',
                'nutriments': {
                    'energy-kcal_100g': 500, 'proteins_100g': 6,
                    'carbohydrates_100g': 55, 'fat_100g': 30,
                },
                'serving_size': '15 g',
                'serving_quantity': 15,
            },
        }
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/barcode/3017624010701/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['per100']['calories'], 500)
        self.assertEqual(response.data['serving_grams'], 15)

    def test_barcode_rejects_bad_input(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/barcode/abc123/')
        self.assertEqual(response.status_code, 400)    