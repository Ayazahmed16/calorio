import io
import json
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from . import services
from .models import (ActivityEntry, ApiToken, DailyGoal, FavoriteFood, Food, MealEntry, SavedMeal, WaterLog,
                     WeightEntry)
from .tests import BaseCase


class WeightTests(BaseCase):
    def test_log_updates_same_day_and_validates(self):
        url = reverse('weight')
        self.client.post(url, {'date': self.today, 'weight_kg': '80.4'})
        self.client.post(url, {'date': self.today, 'weight_kg': '79.9'})
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)
        self.assertEqual(WeightEntry.objects.get().weight_kg, 79.9)
        self.assertEqual(self.client.post(url, {'date': self.today, 'weight_kg': '5'}).status_code, 200)
        self.assertEqual(self.client.post(url, {'date': self.today + timedelta(days=1), 'weight_kg': '80'}).status_code, 200)

    def test_chart_and_change(self):
        for i, kg in enumerate([82, 81, 80]):
            WeightEntry.objects.create(user=self.user, date=self.today - timedelta(days=40 - i * 20), weight_kg=kg)
        r = self.client.get(reverse('weight'))
        self.assertIsNotNone(r.context['chart'])
        self.assertEqual(r.context['change_30d'], -2.0)     # 80 kg today vs 82 kg at the last entry 30+ days ago

    def test_other_users_entry_protected(self):
        e = WeightEntry.objects.create(user=self.other, date=self.today, weight_kg=70)
        self.assertEqual(self.client.post(reverse('delete_weight', args=[e.pk])).status_code, 404)


class WaterTests(BaseCase):
    def test_add_undo_and_clamp(self):
        url = reverse('add_water')
        self.client.post(url, {'amount_ml': 500})
        self.client.post(url, {'amount_ml': 250})
        self.assertEqual(WaterLog.objects.get().amount_ml, 750)
        self.client.post(url, {'amount_ml': -5000})
        self.assertEqual(WaterLog.objects.get().amount_ml, 0)
        self.assertEqual(self.client.post(url, {'amount_ml': 0}).status_code, 302)
        self.assertEqual(WaterLog.objects.get().amount_ml, 0)

    def test_get_not_allowed_and_open_redirect_blocked(self):
        self.assertEqual(self.client.get(reverse('add_water')).status_code, 405)
        r = self.client.post(reverse('add_water'), {'amount_ml': 250, 'next': 'https://evil.example'})
        self.assertEqual(r['Location'], reverse('dashboard'))


class FavoritesAndSavedMealTests(BaseCase):
    def test_favorite_toggle_and_quick_picks(self):
        self.client.post(reverse('toggle_favorite', args=[self.food.pk]), {'next': '/foods/'})
        self.assertTrue(FavoriteFood.objects.filter(user=self.user, food=self.food).exists())
        r = self.client.get(reverse('add_meal'))
        self.assertEqual(r.context['quick'][0]['id'], self.food.id)
        self.assertTrue(r.context['quick'][0]['favorite'])
        self.client.post(reverse('toggle_favorite', args=[self.food.pk]))
        self.assertFalse(FavoriteFood.objects.filter(user=self.user).exists())

    def test_prefill_from_query(self):
        r = self.client.get(reverse('add_meal') + f'?food={self.food.id}&qty=150&type=dinner')
        self.assertEqual(r.context['rows']['protein'], [{'food': str(self.food.id), 'qty': '150', 'error': ''}])
        self.assertEqual(r.context['header'].initial['meal_type'], 'dinner')

    def test_save_and_relog_meal(self):
        for q in (100, 50):
            MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=q, meal_type='lunch', date=self.today)
        r = self.client.post(reverse('saved_meals'), {'name': 'Usual lunch', 'date': self.today, 'meal_type': 'lunch'})
        self.assertEqual(r.status_code, 302)
        saved = SavedMeal.objects.get()
        self.assertEqual(saved.items.get().quantity_grams, 150)         # same food merged
        yesterday = self.today - timedelta(days=1)
        self.client.post(reverse('log_saved_meal', args=[saved.pk]), {'meal_type': 'dinner', 'date': yesterday})
        self.assertTrue(MealEntry.objects.filter(date=yesterday, meal_type='dinner', quantity_grams=150).exists())

    def test_saved_meal_needs_logged_foods(self):
        r = self.client.post(reverse('saved_meals'), {'name': 'Empty', 'date': self.today, 'meal_type': 'snack'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SavedMeal.objects.count(), 0)

    def test_cannot_log_other_users_saved_meal(self):
        saved = SavedMeal.objects.create(user=self.other, name='Theirs')
        self.assertEqual(self.client.post(reverse('log_saved_meal', args=[saved.pk]), {'meal_type': 'lunch'}).status_code, 404)


class CustomFoodTests(BaseCase):
    def test_users_only_see_shared_and_own_foods(self):
        Food.objects.create(name='My shake', calories=100, protein=20, carbs=5, fat=1, owner=self.user)
        theirs = Food.objects.create(name='Their pie', calories=300, protein=3, carbs=40, fat=10, owner=self.other)
        names = {f.name for f in Food.objects.visible_to(self.user)}
        self.assertIn('My shake', names)
        self.assertIn('Chicken', names)
        self.assertNotIn('Their pie', names)
        self.assertEqual(self.client.get(reverse('edit_food', args=[theirs.pk])).status_code, 404)
        r = self.client.post(reverse('add_meal'), {'protein_food': [theirs.pk], 'protein_qty': ['100'],
                                                   'meal_type': 'lunch', 'date': self.today})
        self.assertEqual(r.status_code, 200)       # not one of this user's foods
        self.assertEqual(MealEntry.objects.count(), 0)

    def test_user_food_owned_and_editable_by_owner(self):
        self.client.post(reverse('add_food'), {'name': 'Protein bar', 'calories': 350, 'protein': 30, 'carbs': 30, 'fat': 10})
        food = Food.objects.get(name='Protein bar')
        self.assertEqual(food.owner, self.user)
        r = self.client.post(reverse('edit_food', args=[food.pk]), {
            'name': 'Protein bar XL', 'calories': 400, 'protein': 30, 'carbs': 30, 'fat': 10})
        self.assertEqual(r.status_code, 302)
        self.client.post(reverse('delete_food', args=[food.pk]))
        self.assertFalse(Food.objects.filter(pk=food.pk).exists())

    def test_same_name_allowed_for_different_users(self):
        Food.objects.create(name='Smoothie', calories=90, protein=2, carbs=20, fat=0, owner=self.other)
        r = self.client.post(reverse('add_food'), {'name': 'Smoothie', 'calories': 90, 'protein': 2, 'carbs': 20, 'fat': 0})
        self.assertEqual(r.status_code, 302)

    def test_staff_food_is_shared(self):
        self.user.is_staff = True
        self.user.save()
        self.client.post(reverse('add_food'), {'name': 'Rice', 'calories': 130, 'protein': 3, 'carbs': 28, 'fat': 0})
        self.assertIsNone(Food.objects.get(name='Rice').owner)


class CalculatorTests(BaseCase):
    DATA = {'sex': 'male', 'age': 30, 'height_cm': 180, 'weight_kg': 80, 'activity': '1.55', 'goal': 'lose'}

    def test_math(self):
        r = services.calculate_targets('male', 30, 180, 80, '1.55', 'maintain')
        self.assertEqual(r['bmr'], 1780)          # 800 + 1125 - 150 + 5
        self.assertEqual(r['tdee'], 2759)
        self.assertEqual(services.calculate_targets('male', 30, 180, 80, '1.55', 'lose')['calories'], 2260)
        self.assertEqual(services.calculate_targets('female', 60, 150, 40, '1.2', 'lose')['calories'], 1200)  # safety floor

    def test_view_and_apply(self):
        r = self.client.post(reverse('calculator'), self.DATA)
        self.assertEqual(r.context['result']['calories'], 2260)
        self.assertEqual(DailyGoal.objects.filter(user=self.user).count(), 0)      # calculating alone changes nothing
        self.client.post(reverse('calculator'), {**self.DATA, 'apply': 1})
        goal = DailyGoal.objects.get(user=self.user)
        self.assertEqual((goal.target_calories, goal.target_protein), (2260, 160))

    def test_rejects_bad_input(self):
        self.assertIsNone(self.client.post(reverse('calculator'), {**self.DATA, 'age': 5}).context['result'])


class StreakTests(BaseCase):
    def test_streak_rules(self):
        def log(days_ago):
            MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=1, meal_type='lunch',
                                     date=self.today - timedelta(days=days_ago))
        self.assertEqual(services.logging_streak(self.user), 0)
        for d in (0, 1, 2, 4):
            log(d)
        self.assertEqual(services.logging_streak(self.user), 3)
        self.assertEqual(services.best_streak(self.user), 3)
        MealEntry.objects.filter(date=self.today).delete()
        self.assertEqual(services.logging_streak(self.user), 2)       # today empty but not broken yet


class CsvTests(BaseCase):
    def upload(self, kind, text):
        f = SimpleUploadedFile('data.csv', text.encode(), content_type='text/csv')
        return self.client.post(reverse('import_csv'), {'kind': kind, 'file': f}, follow=True)

    def test_export_meals_and_formula_neutralised(self):
        evil = Food.objects.create(name='=cmd|calc', calories=1, protein=0, carbs=0, fat=0, owner=self.user)
        MealEntry.objects.create(user=self.user, food=evil, quantity_grams=100, meal_type='lunch', date=self.today)
        r = self.client.get(reverse('export_csv', args=['meals']))
        self.assertEqual(r['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn("'=cmd|calc", r.content.decode())

    def test_export_only_own_rows(self):
        WeightEntry.objects.create(user=self.other, date=self.today, weight_kg=99)
        self.assertNotIn('99', self.client.get(reverse('export_csv', args=['weight'])).content.decode())

    def test_import_meals_ok(self):
        r = self.upload('meals', f'date,meal_type,food,quantity_grams\n{self.today},lunch,chicken,200\n{self.today},dinner,Chicken,100\n')
        self.assertEqual(MealEntry.objects.count(), 2)
        self.assertContains(r, 'Imported 2 meals')

    def test_import_is_all_or_nothing(self):
        r = self.upload('meals', f'date,meal_type,food,quantity_grams\n{self.today},lunch,Chicken,200\n{self.today},lunch,Unicorn,100\n')
        self.assertEqual(MealEntry.objects.count(), 0)
        self.assertContains(r, 'Nothing was imported')

    def test_import_activity_weight_and_missing_columns(self):
        self.upload('activity', f'date,steps,calories_burned\n{self.today},5000,200\n')
        self.assertEqual(ActivityEntry.objects.get().steps, 5000)
        self.upload('weight', f'date,weight_kg\n{self.today},81.2\n')
        self.assertEqual(WeightEntry.objects.get().weight_kg, 81.2)
        r = self.upload('weight', 'date\n2026-01-01\n')
        self.assertContains(r, 'Missing column')

    def test_import_rejects_invalid_rows(self):
        r = self.upload('activity', f'date,steps,calories_burned\n{self.today},-5,10\n')
        self.assertEqual(ActivityEntry.objects.count(), 0)
        self.assertContains(r, 'Nothing was imported')


class FoodLookupTests(BaseCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch('tracker.integrations.usda_search', return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    PRODUCT = {'code': '3017620422003', 'product_name': 'Hazelnut spread', 'brands': 'Acme, Other',
               'nutriments': {'energy-kcal_100g': 539, 'proteins_100g': 6.3, 'carbohydrates_100g': 57.5, 'fat_100g': 30.9}}

    def test_barcode_lookup_normalises(self):
        with mock.patch.object(services, '_get_json', return_value={'status': 1, 'product': self.PRODUCT}):
            r = self.client.get(reverse('food_lookup') + '?barcode=3017620422003')
        item = r.json()['results'][0]
        self.assertEqual(item['name'], 'Hazelnut spread (Acme)')
        self.assertEqual(item['calories'], 539)

    def test_search_skips_unusable_and_handles_outage(self):
        with mock.patch.object(services, '_get_json', return_value={'hits': [self.PRODUCT, {'product_name': 'No data'}]}):
            self.assertEqual(len(self.client.get(reverse('food_lookup') + '?q=spread').json()['results']), 1)
        with mock.patch.object(services, '_get_json', return_value=None):
            self.assertEqual(self.client.get(reverse('food_lookup') + '?q=spread').json()['results'], [])

    def test_invalid_barcode_makes_no_request(self):
        with mock.patch.object(services, '_get_json') as m:
            self.client.get(reverse('food_lookup') + '?barcode=12')
            self.client.get(reverse('food_lookup') + '?q=a')
        m.assert_not_called()

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('food_lookup') + '?q=abc').status_code, 302)


class ApiTests(BaseCase):
    def setUp(self):
        super().setUp()
        self.token = ApiToken.objects.create(user=self.user).key
        self.auth = {'HTTP_AUTHORIZATION': f'Token {self.token}'}
        self.api = self.client_class()           # token-only client, no session

    def post(self, name, data):
        return self.api.post(reverse(name), json.dumps(data), content_type='application/json', **self.auth)

    def test_requires_auth(self):
        self.assertEqual(self.api.get(reverse('api_summary')).status_code, 401)
        self.assertEqual(self.api.get(reverse('api_summary'), HTTP_AUTHORIZATION='Token nope').status_code, 401)

    def test_session_cannot_write(self):
        r = self.client.post(reverse('api_meals'), json.dumps({}), content_type='application/json')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.client.get(reverse('api_summary')).status_code, 200)      # read-only is fine

    def test_create_and_summary(self):
        r = self.post('api_meals', {'food': self.food.id, 'quantity_grams': 200, 'meal_type': 'lunch', 'date': str(self.today)})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['calories'], 330.0)
        s = self.api.get(reverse('api_summary'), **self.auth).json()
        self.assertEqual(s['calories'], 330.0)
        self.assertEqual(s['goals']['calories'], 2000)

    def test_validation_errors_are_json(self):
        r = self.post('api_meals', {'food': self.food.id, 'quantity_grams': -1, 'meal_type': 'lunch', 'date': str(self.today)})
        self.assertEqual(r.status_code, 400)
        self.assertIn('quantity_grams', r.json()['fields'])
        r = self.api.post(reverse('api_meals'), 'not json', content_type='application/json', **self.auth)
        self.assertEqual(r.status_code, 400)

    def test_isolated_between_users(self):
        m = MealEntry.objects.create(user=self.other, food=self.food, quantity_grams=100, meal_type='lunch', date=self.today)
        self.assertEqual(self.api.get(reverse('api_meal_detail', args=[m.pk]), **self.auth).status_code, 404)
        self.assertEqual(self.api.delete(reverse('api_meal_detail', args=[m.pk]), **self.auth).status_code, 404)
        self.assertEqual(self.api.get(reverse('api_meals'), **self.auth).json()['results'], [])

    def test_activity_weight_water_foods(self):
        self.post('api_activity', {'steps': 1000, 'calories_burned': 50, 'date': str(self.today)})
        r = self.post('api_activity', {'steps': 500, 'calories_burned': 25, 'date': str(self.today)})
        self.assertEqual((r.status_code, r.json()['steps']), (200, 1500))
        self.assertEqual(self.post('api_weight', {'date': str(self.today), 'weight_kg': 80}).status_code, 201)
        self.assertEqual(self.post('api_weight', {'date': str(self.today), 'weight_kg': 79}).status_code, 200)
        self.assertEqual(self.post('api_water', {'amount_ml': 300}).json()['amount_ml'], 300)
        self.assertEqual(self.api.get(reverse('api_foods') + '?q=chick', **self.auth).json()['results'][0]['name'], 'Chicken')

    def test_wrong_method(self):
        self.assertEqual(self.api.delete(reverse('api_summary'), **self.auth).status_code, 405)

    def test_regenerate_invalidates_old_token(self):
        self.client.post(reverse('regenerate_token'))
        self.assertEqual(self.api.get(reverse('api_summary'), **self.auth).status_code, 401)


class AddFoodFromMealFormTests(BaseCase):
    FOOD = {'name': 'Banana', 'calories': 89, 'protein': 1.1, 'carbs': 23, 'fat': 0.3}

    def test_meal_form_has_searchable_food_box(self):
        self.assertContains(self.client.get(reverse('add_meal')), 'meal-form')

    def test_name_is_prefilled_and_next_carried(self):
        r = self.client.get(reverse('add_food') + f'?name=Banana&next={reverse("add_meal")}')
        self.assertEqual(r.context['form'].initial['name'], 'Banana')
        self.assertContains(r, f'name="next" value="{reverse("add_meal")}"')

    def test_saving_returns_to_meal_form_with_food_selected(self):
        r = self.client.post(reverse('add_food'), {**self.FOOD, 'next': reverse('add_meal')})
        food = Food.objects.get(name='Banana')
        self.assertRedirects(r, f"{reverse('add_meal')}?food={food.id}")
        page = self.client.get(r['Location'])
        group = food.category if food.category in page.context['rows'] else 'other'
        self.assertEqual(page.context['rows'][group][0]['food'], str(food.id))

    def test_external_next_is_ignored(self):
        r = self.client.post(reverse('add_food'), {**self.FOOD, 'next': 'https://evil.example/'})
        self.assertRedirects(r, reverse('food_list'))


class FoodImageTests(BaseCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch('tracker.integrations.usda_search', return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    FOOD = {'name': 'Banana', 'calories': 89, 'protein': 1.1, 'carbs': 23, 'fat': 0.3}
    WIKI = {'type': 'standard', 'description': 'Edible fruit', 'extract': 'A banana is an elongated fruit.',
            'thumbnail': {'source': 'https://upload.wikimedia.org/banana.jpg'}}

    def test_find_food_image_accepts_food_pages_only(self):
        with mock.patch.object(services, '_get_json', return_value=self.WIKI):
            self.assertEqual(services.find_food_image('Banana'), 'https://upload.wikimedia.org/banana.jpg')
        band = {**self.WIKI, 'description': 'American rock band', 'extract': 'Formed in Seattle in 1990.'}
        with mock.patch.object(services, '_get_json', return_value=band):
            self.assertEqual(services.find_food_image('Nirvana'), '')
        with mock.patch.object(services, '_get_json', return_value={**self.WIKI, 'type': 'disambiguation'}):
            self.assertEqual(services.find_food_image('Mercury'), '')
        with mock.patch.object(services, '_get_json', return_value=None):
            self.assertEqual(services.find_food_image('Banana'), '')
        with mock.patch.object(services, '_get_json') as m:
            self.assertEqual(services.find_food_image('ab'), '')
            m.assert_not_called()

    def test_http_thumbnail_rejected(self):
        with mock.patch.object(services, '_get_json', return_value={**self.WIKI, 'thumbnail': {'source': 'http://x/y.jpg'}}):
            self.assertEqual(services.find_food_image('Banana'), '')

    def test_new_food_gets_photo_automatically(self):
        with mock.patch('tracker.views.find_food_image', return_value='https://upload.wikimedia.org/banana.jpg'):
            self.client.post(reverse('add_food'), self.FOOD)
        self.assertEqual(Food.objects.get(name='Banana').image_url, 'https://upload.wikimedia.org/banana.jpg')

    def test_explicit_photo_is_kept_and_lookup_skipped(self):
        with mock.patch('tracker.views.find_food_image') as m:
            self.client.post(reverse('add_food'), {**self.FOOD, 'image_url': 'https://example.com/b.jpg'})
        m.assert_not_called()
        self.assertEqual(Food.objects.get(name='Banana').image_url, 'https://example.com/b.jpg')

    def test_non_https_photo_rejected(self):
        r = self.client.post(reverse('add_food'), {**self.FOOD, 'image_url': 'http://example.com/b.jpg'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Food.objects.filter(name='Banana').exists())

    def test_meal_form_exposes_food_data_for_preview(self):
        Food.objects.create(name='Mango', calories=60, protein=1, carbs=15, fat=0.4, owner=self.user,
                            image_url='https://example.com/m.jpg')
        Food.objects.create(name='Hidden', calories=1, protein=0, carbs=0, fat=0, owner=self.other)
        r = self.client.get(reverse('add_meal'))
        data = {f['name']: f for f in r.context['food_data']}
        self.assertEqual(data['Mango']['image'], 'https://example.com/m.jpg')
        self.assertEqual(data['Mango']['emoji'], '🥭')
        self.assertEqual(data['Chicken']['emoji'], '🍗')
        self.assertNotIn('Hidden', data)
        self.assertContains(r, 'food-data')

    def test_emoji_fallbacks(self):
        from .foodicons import DEFAULT, emoji_for
        self.assertEqual(emoji_for('Grilled Chicken Breast'), '🍗')
        self.assertEqual(emoji_for('Sweet potato'), '🍠')
        self.assertEqual(emoji_for('Quinoa bowl'), DEFAULT)
        self.assertEqual(emoji_for(''), DEFAULT)

    def test_online_suggestion_prefills_add_food_and_lookup_includes_image(self):
        r = self.client.get(reverse('add_food') + '?name=Oat+bar&calories=400&protein=8&carbs=60&fat=12&image_url=https://a.b/c.jpg')
        init = r.context['form'].initial
        self.assertEqual((init['name'], init['calories'], init['image_url']), ('Oat bar', '400', 'https://a.b/c.jpg'))
        product = {'code': '3017620422003', 'product_name': 'Spread', 'brands': '',
                   'image_front_small_url': 'https://images.example/p.jpg', 'nutriments': {'energy-kcal_100g': 500}}
        with mock.patch.object(services, '_get_json', return_value={'hits': [product]}):
            res = self.client.get(reverse('food_lookup') + '?q=spread').json()['results']
        self.assertEqual(res[0]['image'], 'https://images.example/p.jpg')

    def test_thumbnails_render_in_lists(self):
        food = Food.objects.create(name='Mango', calories=60, protein=1, carbs=15, fat=0.4, owner=self.user,
                                   image_url='https://example.com/m.jpg')
        MealEntry.objects.create(user=self.user, food=food, quantity_grams=100, meal_type='snack', date=self.today)
        for name in ('meal_list', 'dashboard', 'food_list'):
            self.assertContains(self.client.get(reverse(name)), 'https://example.com/m.jpg', msg_prefix=name)


class PwaAndEmailTests(BaseCase):
    def test_manifest_and_service_worker(self):
        m = self.client.get(reverse('manifest'))
        self.assertEqual(m['Content-Type'], 'application/manifest+json')
        self.assertEqual(m.json()['display'], 'standalone')
        sw = self.client.get(reverse('service_worker'))
        self.assertEqual(sw['Service-Worker-Allowed'], '/')
        self.assertIn('fetch', sw.content.decode())
        self.assertEqual(self.client.get(reverse('offline')).status_code, 200)

    def test_pages_link_manifest(self):
        self.assertContains(self.client.get(reverse('dashboard')), 'rel="manifest"')

    def test_icons_exist(self):
        from django.contrib.staticfiles import finders
        for n in ('icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png'):
            self.assertIsNotNone(finders.find(f'tracker/icons/{n}'), n)

    def test_weekly_summary_email(self):
        self.user.email = 'ayaz@example.com'
        self.user.save()
        MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=200, meal_type='lunch', date=self.today)
        call_command('send_weekly_summary', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Average calories: 330', mail.outbox[0].body)

    def test_weekly_summary_skips_quiet_users(self):
        self.user.email = 'ayaz@example.com'
        self.user.save()
        call_command('send_weekly_summary', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 0)
