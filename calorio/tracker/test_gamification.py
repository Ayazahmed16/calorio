from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .gamification import award_badges, compute_stats, current_streak, longest_streak
from .models import Badge, Meal


class StreakMathTests(TestCase):
    def test_current_streak_counts_back_from_today(self):
        today = date(2026, 10, 4)
        days = {today, today - timedelta(days=1), today - timedelta(days=2)}
        self.assertEqual(current_streak(days, today), 3)

    def test_streak_survives_until_day_ends(self):
        today = date(2026, 10, 4)
        days = {today - timedelta(days=1), today - timedelta(days=2)}
        self.assertEqual(current_streak(days, today), 2)

    def test_gap_breaks_streak(self):
        today = date(2026, 10, 4)
        days = {today, today - timedelta(days=2)}
        self.assertEqual(current_streak(days, today), 1)

    def test_longest_streak(self):
        d = date(2026, 10, 1)
        days = {d, d + timedelta(days=1), d + timedelta(days=2), d + timedelta(days=5)}
        self.assertEqual(longest_streak(days), 3)


class BadgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('a', password='pass12345')
        self.other = User.objects.create_user('b', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def log_on(self, user, days_ago):
        meal = Meal.objects.create(user=user, name='x', calories=100, protein=30)
        Meal.objects.filter(pk=meal.pk).update(eaten_at=timezone.now() - timedelta(days=days_ago))

    def test_first_meal_badge_awarded_by_signal(self):
        Meal.objects.create(user=self.user, name='x', calories=100)
        self.assertTrue(Badge.objects.filter(user=self.user, code='first_meal').exists())

    def test_three_day_streak_badge(self):
        for n in range(3):
            self.log_on(self.user, n)
        award_badges(self.user)
        self.assertTrue(Badge.objects.filter(user=self.user, code='log_3').exists())

    def test_other_users_meals_do_not_count(self):
        for n in range(3):
            self.log_on(self.other, n)
        self.assertEqual(compute_stats(self.user)['logging']['best'], 0)

    def test_endpoint_lists_badges(self):
        Meal.objects.create(user=self.user, name='x', calories=100)
        response = self.client.get('/api/streaks/')
        self.assertEqual(response.status_code, 200)
        earned = {b['code']: b['earned'] for b in response.data['badges']}
        self.assertTrue(earned['first_meal'])
        self.assertFalse(earned['log_7'])

    def test_endpoint_requires_login(self):
        response = APIClient().get('/api/streaks/')
        self.assertIn(response.status_code, [401, 403])