from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Meal


class RecipeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('a', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('tracker.recipe_view.suggest_recipes')
    def test_drops_over_budget_and_ranks_by_fit(self, mock_ai):
        mock_ai.return_value = {'recipes': [
            {'name': 'Too big', 'calories': 3000, 'protein': 50, 'carbs': 1, 'fat': 1, 'steps': ['x']},
            {'name': 'Low protein', 'calories': 500, 'protein': 5, 'carbs': 1, 'fat': 1, 'steps': ['x']},
            {'name': 'High protein', 'calories': 500, 'protein': 40, 'carbs': 1, 'fat': 1, 'steps': ['x']},
        ]}
        response = self.client.post('/api/recipes/', {'ingredients': 'eggs, rice'}, format='json')
        self.assertEqual(response.status_code, 200)
        names = [r['name'] for r in response.data['recipes']]
        self.assertEqual(names, ['High protein', 'Low protein'])

    def test_requires_ingredients(self):
        response = self.client.post('/api/recipes/', {'ingredients': '  , '}, format='json')
        self.assertEqual(response.status_code, 400)

    @patch('tracker.recipe_view.suggest_recipes')
    def test_no_recipes_when_goal_reached(self, mock_ai):
        Meal.objects.create(user=self.user, name='x', calories=2000, protein=100)
        response = self.client.post('/api/recipes/', {'ingredients': 'eggs'}, format='json')
        self.assertEqual(response.data['recipes'], [])
        mock_ai.assert_not_called()