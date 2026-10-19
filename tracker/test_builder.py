from datetime import timedelta

from django.urls import reverse

from .models import Food, MealEntry
from .tests import BaseCase


class MealBuilderTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.rice = Food.objects.create(name='White rice', calories=130, protein=2.7, carbs=28, fat=0.3)
        self.oil = Food.objects.create(name='Olive oil', calories=884, protein=0, carbs=0, fat=100)
        self.spinach = Food.objects.create(name='Spinach', calories=23, protein=2.9, carbs=3.6, fat=0.4)

    def post(self, **extra):
        data = {'meal_type': 'dinner', 'date': self.today,
                'protein_food': [self.food.id, ''], 'protein_qty': ['200', ''],
                'carbs_food': [self.rice.id], 'carbs_qty': ['150'],
                'fats_food': [self.oil.id], 'fats_qty': ['10']}
        data.update(extra)
        return self.client.post(reverse('add_meal'), data)

    def test_categories_are_detected(self):
        self.assertEqual(self.food.category, 'protein')
        self.assertEqual(self.rice.category, 'carbs')
        self.assertEqual(self.oil.category, 'fats')
        self.assertEqual(self.spinach.category, 'other')
        explicit = Food.objects.create(name='Mystery', calories=100, protein=1, carbs=1, fat=1, category='fats')
        self.assertEqual(explicit.category, 'fats')

    def test_one_save_logs_every_food_as_one_meal(self):
        r = self.post()
        entries = MealEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 3)
        self.assertEqual({e.meal_type for e in entries}, {'dinner'})
        self.assertEqual({e.date for e in entries}, {self.today})
        self.assertEqual(round(sum(e.total_calories() for e in entries)), 330 + 195 + 88)
        ids = ','.join(str(e.id) for e in entries.order_by('id'))
        self.assertRedirects(r, f"{reverse('meal_list')}?new={ids}", fetch_redirect_response=False)
        self.assertContains(self.client.get(r['Location']), 'flash')

    def test_blank_rows_are_ignored_but_half_filled_rows_fail(self):
        r = self.post(protein_food=[self.food.id, self.food.id], protein_qty=['200', ''])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MealEntry.objects.count(), 0)                  # nothing saved if any row is wrong
        errors = [x['error'] for x in r.context['rows']['protein']]
        self.assertEqual(errors, ['', 'Enter the amount in grams.'])

    def test_row_validation_and_values_are_kept_for_redisplay(self):
        r = self.post(carbs_qty=['-3'])
        self.assertEqual(r.status_code, 200)
        self.assertIn('between 0.1 and 5000', r.context['rows']['carbs'][0]['error'])
        self.assertEqual(r.context['rows']['protein'][0]['qty'], '200')   # the other rows survive
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_needs_at_least_one_food(self):
        r = self.client.post(reverse('add_meal'), {'meal_type': 'lunch', 'date': self.today})
        self.assertEqual(r.status_code, 200)
        self.assertIn('at least one food', r.context['error'])

    def test_future_date_and_bad_meal_type_rejected(self):
        self.assertEqual(self.post(date=self.today + timedelta(days=1)).status_code, 200)
        self.assertEqual(self.post(meal_type='brunch').status_code, 200)
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_other_users_foods_cannot_be_used(self):
        theirs = Food.objects.create(name='Secret', calories=1, protein=0, carbs=0, fat=0, owner=self.other)
        r = self.post(protein_food=[theirs.id], protein_qty=['100'], carbs_food=[], carbs_qty=[],
                      fats_food=[], fats_qty=[])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_row_count_is_capped(self):
        many = [self.food.id] * 30
        self.post(protein_food=many, protein_qty=['10'] * 30, carbs_food=[], carbs_qty=[], fats_food=[], fats_qty=[])
        self.assertEqual(MealEntry.objects.count(), 12)

    def test_prefill_places_food_in_its_group(self):
        r = self.client.get(reverse('add_meal') + f'?food={self.oil.id}&qty=15')
        self.assertEqual(r.context['rows']['fats'][0]['qty'], '15')
        r = self.client.get(reverse('add_meal') + f'?food={self.spinach.id}')
        self.assertEqual(len(r.context['rows']['other']), 1)

    def test_page_exposes_groups_and_food_data(self):
        r = self.client.get(reverse('add_meal'))
        self.assertEqual([g['key'] for g in r.context['groups']], ['protein', 'carbs', 'fats', 'other'])
        cats = {f['name']: f['category'] for f in r.context['food_data']}
        self.assertEqual((cats['White rice'], cats['Olive oil']), ('carbs', 'fats'))

    def test_food_form_group_can_be_chosen_or_auto(self):
        self.client.post(reverse('add_food'), {'name': 'Ghee', 'calories': 900, 'protein': 0, 'carbs': 0, 'fat': 100, 'category': ''})
        self.assertEqual(Food.objects.get(name='Ghee').category, 'fats')
        self.client.post(reverse('add_food'), {'name': 'Odd thing', 'calories': 100, 'protein': 5, 'carbs': 5, 'fat': 1, 'category': 'carbs'})
        self.assertEqual(Food.objects.get(name='Odd thing').category, 'carbs')

    def test_edit_single_meal_still_works(self):
        m = MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=100, meal_type='lunch', date=self.today)
        r = self.client.post(reverse('edit_meal', args=[m.pk]), {
            'food': self.rice.id, 'quantity_grams': '250', 'meal_type': 'dinner', 'date': self.today})
        self.assertEqual(r.status_code, 302)
        m.refresh_from_db()
        self.assertEqual((m.food, m.quantity_grams), (self.rice, 250))
