from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Food, Meal
from .suggestions import suggest_meals


class SuggestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('a', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_never_exceeds_remaining_calories(self):
        foods = [
            Food.objects.create(name='A', calories=300, protein=10),
            Food.objects.create(name='B', calories=500, protein=30),
            Food.objects.create(name='C', calories=900, protein=50),
        ]
        results = suggest_meals(foods, left_cal=600, left_protein=40)
        self.assertTrue(results)
        for r in results:
            self.assertLessEqual(r['calories'], 600)

    def test_prefers_meal_that_covers_protein(self):
        low = Food.objects.create(name='Low protein', calories=500, protein=2)
        high = Food.objects.create(name='High protein', calories=500, protein=40)
        results = suggest_meals([low, high], left_cal=600, left_protein=40)
        self.assertEqual(results[0]['items'][0]['food'].name, 'High protein')

    def test_endpoint_uses_goal_and_todays_meals(self):
        Food.objects.create(name='Roti', calories=120, protein=3.5)
        Meal.objects.create(user=self.user, name='x', calories=1900, protein=90)
        response = self.client.get('/api/suggestions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['left']['calories'], 100)