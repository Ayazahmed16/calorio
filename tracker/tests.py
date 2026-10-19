from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ActivityEntry, DailyGoal, Food, MealEntry


class BaseCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('ayaz', password='pass12345!')
        self.other = User.objects.create_user('sam', password='pass12345!')
        self.food = Food.objects.create(name='Chicken', calories=165, protein=31, carbs=0, fat=3.6)
        self.today = timezone.localdate()
        self.client.login(username='ayaz', password='pass12345!')
        # keep the suite offline: never call the live photo service from tests
        patcher = mock.patch('tracker.views.find_food_image', return_value='')
        patcher.start()
        self.addCleanup(patcher.stop)


class AuthTests(BaseCase):
    def test_pages_require_login(self):
        self.client.logout()
        for name in ['dashboard', 'meal_list', 'add_meal', 'activity_list', 'add_activity',
                     'food_list', 'goals', 'analytics']:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn('/accounts/login/', r['Location'])

    def test_signup_creates_user_goal_and_logs_in(self):
        self.client.logout()
        r = self.client.post(reverse('signup'), {
            'username': 'newbie', 'password1': 'Str0ng!pass99', 'password2': 'Str0ng!pass99'})
        self.assertRedirects(r, reverse('dashboard'))
        user = User.objects.get(username='newbie')
        self.assertTrue(DailyGoal.objects.filter(user=user).exists())
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_signup_rejects_mismatched_passwords(self):
        self.client.logout()
        r = self.client.post(reverse('signup'), {
            'username': 'newbie', 'password1': 'Str0ng!pass99', 'password2': 'different'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username='newbie').exists())

    def test_landing_redirects_when_logged_in(self):
        self.assertRedirects(self.client.get('/'), reverse('dashboard'))


class MealTests(BaseCase):
    def post_meal(self, qty='200', **over):
        # the meal builder posts one *_food / *_qty list per group (protein, carbs, fats, other)
        data = {'protein_food': [self.food.id], 'protein_qty': [qty], 'meal_type': 'lunch', 'date': self.today}
        data.update(over)
        return self.client.post(reverse('add_meal'), data)

    def test_add_meal(self):
        self.assertEqual(self.post_meal().status_code, 302)
        meal = MealEntry.objects.get()
        self.assertEqual(meal.user, self.user)
        self.assertEqual(meal.total_calories(), 330.0)

    def test_rejects_bad_quantity(self):
        for bad in ['', '-5', '0', '99999', 'abc']:
            r = self.post_meal(qty=bad)
            self.assertEqual(r.status_code, 200, bad)
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_rejects_future_date(self):
        self.assertEqual(self.post_meal(date=self.today + timedelta(days=2)).status_code, 200)
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_cannot_touch_other_users_meal(self):
        meal = MealEntry.objects.create(user=self.other, food=self.food, quantity_grams=100,
                                        meal_type='lunch', date=self.today)
        self.assertEqual(self.client.get(reverse('edit_meal', args=[meal.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('delete_meal', args=[meal.pk])).status_code, 404)
        self.assertTrue(MealEntry.objects.filter(pk=meal.pk).exists())

    def test_edit_and_delete(self):
        meal = MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=100,
                                        meal_type='lunch', date=self.today)
        r = self.client.post(reverse('edit_meal', args=[meal.pk]), {
            'food': self.food.id, 'quantity_grams': '300', 'meal_type': 'dinner', 'date': self.today})
        self.assertEqual(r.status_code, 302)
        meal.refresh_from_db()
        self.assertEqual(meal.quantity_grams, 300)
        # GET only shows the confirmation page and must not delete
        self.assertEqual(self.client.get(reverse('delete_meal', args=[meal.pk])).status_code, 200)
        self.assertTrue(MealEntry.objects.filter(pk=meal.pk).exists())
        self.client.post(reverse('delete_meal', args=[meal.pk]))
        self.assertFalse(MealEntry.objects.filter(pk=meal.pk).exists())

    def test_list_only_shows_own_meals(self):
        MealEntry.objects.create(user=self.other, food=self.food, quantity_grams=100,
                                 meal_type='lunch', date=self.today)
        r = self.client.get(reverse('meal_list'))
        self.assertEqual(len(r.context['meals']), 0)


class ActivityTests(BaseCase):
    def post_activity(self, **over):
        data = {'steps': 4000, 'calories_burned': '150', 'activity_type': 'walk', 'date': self.today}
        data.update(over)
        return self.client.post(reverse('add_activity'), data)

    def test_second_entry_same_day_merges(self):
        self.post_activity()
        self.post_activity(steps=1000, calories_burned='50')
        self.assertEqual(ActivityEntry.objects.count(), 1)
        a = ActivityEntry.objects.get()
        self.assertEqual(a.steps, 5000)
        self.assertEqual(a.calories_burned, 200)

    def test_rejects_negative_values(self):
        self.assertEqual(self.post_activity(steps=-1).status_code, 200)
        self.assertEqual(self.post_activity(calories_burned='-10').status_code, 200)
        self.assertEqual(ActivityEntry.objects.count(), 0)

    def test_edit_cannot_collide_with_other_day(self):
        self.post_activity()
        yesterday = self.today - timedelta(days=1)
        other = ActivityEntry.objects.create(user=self.user, date=yesterday, steps=10, calories_burned=1)
        r = self.client.post(reverse('edit_activity', args=[other.pk]), {
            'steps': 10, 'calories_burned': '1', 'activity_type': '', 'date': self.today})
        self.assertEqual(r.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.date, yesterday)


class FoodTests(BaseCase):
    def test_any_user_can_add_food(self):
        r = self.client.post(reverse('add_food'), {
            'name': 'Oats', 'calories': 380, 'protein': 13, 'carbs': 66, 'fat': 7})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Food.objects.filter(name='Oats').exists())

    def test_duplicate_and_impossible_macros_rejected(self):
        r = self.client.post(reverse('add_food'), {
            'name': 'chicken', 'calories': 100, 'protein': 10, 'carbs': 10, 'fat': 10})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse('add_food'), {
            'name': 'Magic', 'calories': 100, 'protein': 60, 'carbs': 60, 'fat': 10})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Food.objects.filter(name='Magic').exists())

    def test_only_staff_can_edit_or_delete(self):
        self.client.post(reverse('delete_food', args=[self.food.pk]))
        self.assertTrue(Food.objects.filter(pk=self.food.pk).exists())
        self.user.is_staff = True
        self.user.save()
        self.client.post(reverse('delete_food', args=[self.food.pk]))
        self.assertFalse(Food.objects.filter(pk=self.food.pk).exists())


class GoalTests(BaseCase):
    def test_update_goals(self):
        r = self.client.post(reverse('goals'), {'target_calories': 2400, 'target_protein': 150,
                                                'target_steps': 12000, 'target_water_ml': 2500})
        self.assertRedirects(r, reverse('dashboard'))
        g = DailyGoal.objects.get(user=self.user)
        self.assertEqual((g.target_calories, g.target_protein, g.target_steps, g.target_water_ml),
                         (2400, 150, 12000, 2500))

    def test_rejects_unreasonable_goals(self):
        r = self.client.post(reverse('goals'), {'target_calories': 50, 'target_protein': 150, 'target_steps': 12000})
        self.assertEqual(r.status_code, 200)


class AnalyticsTests(BaseCase):
    def test_totals(self):
        MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=200,
                                 meal_type='lunch', date=self.today)
        ActivityEntry.objects.create(user=self.user, date=self.today, steps=7000, calories_burned=300)
        r = self.client.get(reverse('analytics'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['avg_calories'], 330)
        self.assertEqual(r.context['days_logged'], 1)
        self.assertEqual(r.context['total_burned'], 300)
        self.assertEqual(len(r.context['rows']), 7)

    def test_bad_range_falls_back(self):
        r = self.client.get(reverse('analytics') + '?days=abc')
        self.assertEqual(r.context['days'], 7)
        r = self.client.get(reverse('analytics') + '?days=30')
        self.assertEqual(len(r.context['rows']), 30)

    def test_empty_state(self):
        r = self.client.get(reverse('analytics'))
        self.assertEqual(r.context['avg_calories'], 0)
        self.assertEqual(r.context['protein_share'], 0)

    def test_dashboard_uses_goal(self):
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['goal'].target_calories, 2000)


class CompletenessTests(BaseCase):
    def test_dashboard_other_day_and_future_clamped(self):
        yesterday = self.today - timedelta(days=1)
        MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=100,
                                 meal_type='lunch', date=yesterday)
        r = self.client.get(reverse('dashboard') + f'?date={yesterday}')
        self.assertEqual(r.context['total_calories'], 165)
        self.assertFalse(r.context['is_today'])
        r = self.client.get(reverse('dashboard') + f'?date={self.today + timedelta(days=5)}')
        self.assertTrue(r.context['is_today'])
        r = self.client.get(reverse('dashboard') + '?date=garbage')
        self.assertTrue(r.context['is_today'])

    def test_meal_filters(self):
        MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=100, meal_type='lunch', date=self.today)
        MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=100, meal_type='dinner', date=self.today)
        r = self.client.get(reverse('meal_list') + '?type=dinner')
        self.assertEqual([m.meal_type for m in r.context['meals']], ['dinner'])
        r = self.client.get(reverse('meal_list') + '?type=bogus&from=nope')
        self.assertEqual(len(r.context['meals']), 2)
        r = self.client.get(reverse('meal_list') + f'?from={self.today + timedelta(days=1)}')
        self.assertEqual(len(r.context['meals']), 0)

    def test_activity_date_filter(self):
        ActivityEntry.objects.create(user=self.user, date=self.today, steps=1, calories_burned=1)
        r = self.client.get(reverse('activity_list') + f'?to={self.today - timedelta(days=1)}')
        self.assertEqual(len(r.context['activities']), 0)

    def test_password_reset_sends_email(self):
        from django.core import mail
        self.user.email = 'ayaz@example.com'
        self.user.save()
        self.client.logout()
        r = self.client.post(reverse('password_reset'), {'email': 'ayaz@example.com'})
        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/reset/', mail.outbox[0].body)

    def test_password_reset_unknown_email_does_not_reveal(self):
        self.client.logout()
        r = self.client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
        self.assertRedirects(r, reverse('password_reset_done'))

    def test_password_change(self):
        r = self.client.post(reverse('password_change'), {
            'old_password': 'pass12345!', 'new_password1': 'Br4nd!newpass', 'new_password2': 'Br4nd!newpass'})
        self.assertRedirects(r, reverse('dashboard'))
        self.assertTrue(User.objects.get(username='ayaz').check_password('Br4nd!newpass'))
