import io
from datetime import datetime, timedelta, timezone as dt_tz
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from . import integrations as ext
from .models import ActivityEntry, FitbitConnection, Food, MealEntry, UserSettings, WaterLog, WeightEntry
from .tests import BaseCase

USDA_RESPONSE = {'foods': [
    {'description': 'Bananas, raw', 'foodNutrients': [
        {'nutrientNumber': '208', 'value': 89}, {'nutrientNumber': '203', 'value': 1.09},
        {'nutrientNumber': '205', 'value': 22.8}, {'nutrientNumber': '204', 'value': 0.33}]},
    {'description': 'Banana chips, dehydrated, sweetened, with added vitamins', 'foodNutrients': [
        {'nutrientNumber': '957', 'value': 519}, {'nutrientNumber': '203', 'value': 2.3}]},
    {'description': 'No energy listed', 'foodNutrients': [{'nutrientNumber': '203', 'value': 1}]},
]}

MEAL = {'idMeal': '52772', 'strMeal': 'Teriyaki Chicken Casserole', 'strCategory': 'Chicken', 'strArea': 'Japanese',
        'strMealThumb': 'https://www.themealdb.com/images/media/meals/x.jpg', 'strYoutube': 'https://youtube.com/watch?v=1',
        'strSource': '', 'strInstructions': 'Preheat oven.\r\nMix everything.\r\n\r\nBake.',
        'strIngredient1': 'soy sauce', 'strMeasure1': '3/4 cup', 'strIngredient2': 'chicken breasts', 'strMeasure2': '2',
        'strIngredient3': '', 'strMeasure3': ' '}


class UsdaTests(BaseCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_search_normalises_filters_and_sorts(self):
        with mock.patch.object(ext, 'http_json', return_value=USDA_RESPONSE):
            res = ext.usda_search('banana')
        self.assertEqual([r['name'] for r in res][0], 'Bananas, raw')          # shortest first
        self.assertEqual(res[0]['calories'], 89)
        self.assertEqual(res[0]['source'], 'USDA')
        self.assertEqual(len(res), 2)                                         # entry without energy dropped
        self.assertEqual(res[1]['calories'], 519)                             # Atwater fallback

    def test_results_are_cached(self):
        with mock.patch.object(ext, 'http_json', return_value=USDA_RESPONSE) as m:
            ext.usda_search('banana')
            ext.usda_search('Banana')
        self.assertEqual(m.call_count, 1)

    def test_short_query_and_outage(self):
        with mock.patch.object(ext, 'http_json') as m:
            self.assertEqual(ext.usda_search('a'), [])
            m.assert_not_called()
        with mock.patch.object(ext, 'http_json', side_effect=ext.ApiError('boom', 429)):
            self.assertEqual(ext.usda_search('banana'), [])

    def test_lookup_merges_sources_without_duplicates(self):
        off = [{'name': 'Bananas, raw', 'calories': 90, 'protein': 1, 'carbs': 20, 'fat': 0, 'barcode': '', 'image': ''},
               {'name': 'Banana yoghurt', 'calories': 80, 'protein': 3, 'carbs': 12, 'fat': 2, 'barcode': '1', 'image': ''}]
        with mock.patch.object(ext, 'usda_search', return_value=[{'name': 'Bananas, raw', 'calories': 89, 'protein': 1,
                                                                   'carbs': 22.8, 'fat': 0.3, 'barcode': '', 'image': '', 'source': 'USDA'}]), \
                mock.patch('tracker.services.search_foods', return_value=off):
            data = self.client.get(reverse('food_lookup') + '?q=banana').json()['results']
        names = [r['name'] for r in data]
        self.assertEqual(names, ['Bananas, raw', 'Banana yoghurt'])
        self.assertEqual(data[0]['source'], 'USDA')
        self.assertEqual(data[1]['source'], 'Open Food Facts')


class RecipeTests(BaseCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_detail_parsing(self):
        with mock.patch.object(ext, 'http_json', return_value={'meals': [MEAL]}):
            r = ext.meal_detail('52772')
        self.assertEqual(len(r['ingredients']), 2)                              # blank ingredient skipped
        self.assertEqual(r['instructions'], ['Preheat oven.', 'Mix everything.', 'Bake.'])
        self.assertEqual(r['ingredients'][0], {'name': 'soy sauce', 'measure': '3/4 cup'})

    def test_detail_rejects_non_numeric_ids(self):
        with mock.patch.object(ext, 'http_json') as m:
            self.assertIsNone(ext.meal_detail('abc'))
            m.assert_not_called()

    def test_search_page_and_outage_message(self):
        def fake(url, **kw):
            if 'list.php' in url:
                return {'meals': [{'strCategory': 'Chicken'}, {'strCategory': 'Beef'}]}
            return {'meals': [MEAL]}
        with mock.patch.object(ext, 'http_json', side_effect=fake):
            r = self.client.get(reverse('recipes') + '?q=chicken')
        self.assertContains(r, 'Teriyaki Chicken Casserole')
        self.assertContains(r, 'Beef')
        cache.clear()
        with mock.patch.object(ext, 'http_json', side_effect=ext.ApiError('down')):
            r = self.client.get(reverse('recipes'))
        self.assertContains(r, 'unreachable')

    def test_save_recipe_as_food_converts_to_per_100g(self):
        with mock.patch.object(ext, 'http_json', return_value={'meals': [MEAL]}):
            r = self.client.post(reverse('recipe_detail', args=['52772']), {
                'name': 'Teriyaki casserole', 'serving_g': 400, 'calories': 600, 'protein': 40, 'carbs': 60, 'fat': 20})
        food = Food.objects.get(name='Teriyaki casserole')
        self.assertEqual((food.calories, food.protein, food.carbs, food.fat), (150, 10, 15, 5))
        self.assertEqual(food.owner, self.user)
        self.assertEqual(food.image_url, 'https://www.themealdb.com/images/media/meals/x.jpg')
        self.assertRedirects(r, f"{reverse('add_meal')}?food={food.id}&qty=400", fetch_redirect_response=False)

    def test_save_recipe_validation(self):
        with mock.patch.object(ext, 'http_json', return_value={'meals': [MEAL]}):
            r = self.client.post(reverse('recipe_detail', args=['52772']), {
                'name': 'X', 'serving_g': 100, 'calories': 600, 'protein': 80, 'carbs': 60, 'fat': 20})
        self.assertEqual(r.status_code, 200)                                     # 160 g of macros in a 100 g serving
        self.assertFalse(Food.objects.filter(name='X').exists())

    def test_recipe_not_found_redirects(self):
        with mock.patch.object(ext, 'http_json', return_value={'meals': None}):
            r = self.client.get(reverse('recipe_detail', args=['999']))
        self.assertRedirects(r, reverse('recipes'))


@override_settings(FITBIT_CLIENT_ID='cid', FITBIT_CLIENT_SECRET='secret')
class FitbitTests(BaseCase):
    def test_pkce_challenge_is_s256_of_verifier(self):
        import base64, hashlib
        v, c = ext.new_pkce()
        self.assertEqual(c, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode())
        self.assertGreaterEqual(len(v), 43)

    def test_connect_redirects_with_state_and_pkce(self):
        r = self.client.get(reverse('fitbit_connect'))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r['Location'].startswith('https://www.fitbit.com/oauth2/authorize?'))
        self.assertIn('code_challenge_method=S256', r['Location'])
        self.assertIn(self.client.session['fitbit_state'], r['Location'])

    @override_settings(FITBIT_CLIENT_ID='', FITBIT_CLIENT_SECRET='')
    def test_connect_without_keys_explains(self):
        r = self.client.get(reverse('fitbit_connect'), follow=True)
        self.assertContains(r, 'not configured')

    def test_callback_rejects_bad_state(self):
        self.client.get(reverse('fitbit_connect'))
        r = self.client.get(reverse('fitbit_callback') + '?code=abc&state=forged', follow=True)
        self.assertContains(r, 'could not be verified')
        self.assertFalse(FitbitConnection.objects.exists())

    def test_callback_connects_and_syncs(self):
        self.client.get(reverse('fitbit_connect'))
        state = self.client.session['fitbit_state']
        today = timezone.localdate()

        def fake(url, **kw):
            if url.endswith('/oauth2/token'):
                return {'access_token': 'AT', 'refresh_token': 'RT', 'expires_in': 28800, 'user_id': 'ABC123'}
            if '/activities/date/' in url:
                return {'summary': {'steps': 8000, 'caloriesOut': 2500.4}}
            if '/body/log/weight/' in url:
                return {'weight': [{'date': str(today), 'weight': 80.26}, {'date': 'bad', 'weight': 1}]}
            raise AssertionError(url)
        with mock.patch.object(ext, 'http_json', side_effect=fake):
            r = self.client.get(reverse('fitbit_callback') + f'?code=abc&state={state}', follow=True)
        self.assertContains(r, 'Fitbit connected')
        conn = FitbitConnection.objects.get()
        self.assertEqual((conn.access_token, conn.refresh_token, conn.fitbit_user_id), ('AT', 'RT', 'ABC123'))
        self.assertEqual(ActivityEntry.objects.filter(user=self.user).count(), 7)
        self.assertEqual(ActivityEntry.objects.get(date=today).steps, 8000)
        self.assertEqual(WeightEntry.objects.get().weight_kg, 80.3)

    def test_sync_overwrites_not_duplicates_and_refreshes_expired_token(self):
        today = timezone.localdate()
        ActivityEntry.objects.create(user=self.user, date=today, steps=100, calories_burned=5)
        FitbitConnection.objects.create(user=self.user, access_token='old', refresh_token='RT',
                                        expires_at=timezone.now() - timedelta(hours=1))
        calls = []

        def fake(url, **kw):
            calls.append(url)
            if url.endswith('/oauth2/token'):
                return {'access_token': 'NEW', 'refresh_token': 'RT2', 'expires_in': 3600}
            if '/activities/date/' in url:
                return {'summary': {'steps': 5000, 'caloriesOut': 2000}}
            return {'weight': []}
        with mock.patch.object(ext, 'http_json', side_effect=fake):
            self.client.post(reverse('fitbit_sync'), {'days': 1})
        self.assertEqual(ActivityEntry.objects.filter(date=today).count(), 1)
        self.assertEqual(ActivityEntry.objects.get(date=today).steps, 5000)
        conn = FitbitConnection.objects.get()
        self.assertEqual((conn.access_token, conn.refresh_token), ('NEW', 'RT2'))
        self.assertIsNotNone(conn.last_synced)

    def test_sync_failure_is_reported_not_raised(self):
        FitbitConnection.objects.create(user=self.user, access_token='a', refresh_token='r',
                                        expires_at=timezone.now() + timedelta(hours=1))
        with mock.patch.object(ext, 'http_json', side_effect=ext.ApiError('HTTP 500')):
            r = self.client.post(reverse('fitbit_sync'), {'days': 3}, follow=True)
        self.assertContains(r, 'Fitbit sync failed')

    def test_disconnect_keeps_imported_data(self):
        FitbitConnection.objects.create(user=self.user, access_token='a', refresh_token='r',
                                        expires_at=timezone.now() + timedelta(hours=1))
        ActivityEntry.objects.create(user=self.user, date=timezone.localdate(), steps=1)
        self.client.post(reverse('fitbit_disconnect'))
        self.assertFalse(FitbitConnection.objects.exists())
        self.assertEqual(ActivityEntry.objects.count(), 1)

    def test_actions_require_post(self):
        self.assertEqual(self.client.get(reverse('fitbit_sync')).status_code, 405)
        self.assertEqual(self.client.get(reverse('fitbit_disconnect')).status_code, 405)


@override_settings(TELEGRAM_BOT_TOKEN='123:ABC', TELEGRAM_BOT_USERNAME='CalorioBot', TELEGRAM_WEBHOOK_SECRET='s3cret')
class TelegramTests(BaseCase):
    def update(self, text, chat=555):
        return {'update_id': 1, 'message': {'text': text, 'chat': {'id': chat}}}

    def test_link_flow_and_commands(self):
        self.client.post(reverse('telegram_connect'))
        us = UserSettings.objects.get(user=self.user)
        self.assertTrue(us.telegram_link_code)
        page = self.client.get(reverse('connections'))
        self.assertContains(page, f't.me/CalorioBot?start={us.telegram_link_code}')

        sent = []
        with mock.patch.object(ext, 'tg_send', side_effect=lambda c, t: sent.append((c, t)) or True):
            ext.tg_handle_update(self.update(f'/start {us.telegram_link_code}'))
            us.refresh_from_db()
            self.assertEqual((us.telegram_chat_id, us.telegram_link_code), ('555', ''))
            ext.tg_handle_update(self.update('/water 300'))
            self.assertEqual(WaterLog.objects.get().amount_ml, 300)
            MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=200, meal_type='lunch', date=timezone.localdate())
            ext.tg_handle_update(self.update('/today'))
        self.assertIn('Calories: 330 / 2000', sent[-1][1])
        self.assertIn('Water: 300', sent[-1][1])

    def test_link_code_is_single_use_and_unknown_chats_are_refused(self):
        us = UserSettings.for_user(self.user)
        us.telegram_link_code = 'CODE1'
        us.save()
        with mock.patch.object(ext, 'tg_send', return_value=True) as send:
            ext.tg_handle_update(self.update('/start CODE1', chat=1))
            ext.tg_handle_update(self.update('/start CODE1', chat=2))          # replay from another chat
            ext.tg_handle_update(self.update('/today', chat=999))              # never linked
        us.refresh_from_db()
        self.assertEqual(us.telegram_chat_id, '1')
        self.assertIn('not linked', send.call_args_list[-1].args[1])

    def test_water_validation_and_stop(self):
        us = UserSettings.for_user(self.user)
        us.telegram_chat_id, us.reminders_enabled = '7', True
        us.save()
        with mock.patch.object(ext, 'tg_send', return_value=True) as send:
            ext.tg_handle_update(self.update('/water abc', chat=7))
            ext.tg_handle_update(self.update('/water 99999', chat=7))
            ext.tg_handle_update(self.update('/stop', chat=7))
        self.assertEqual(WaterLog.objects.count(), 0)
        self.assertIn('Usage', send.call_args_list[0].args[1])
        us.refresh_from_db()
        self.assertFalse(us.reminders_enabled)

    def test_webhook_needs_secret(self):
        import json
        body = json.dumps(self.update('/help'))
        self.assertEqual(self.client.post(reverse('telegram_webhook', args=['wrong']), body, content_type='application/json').status_code, 404)
        with mock.patch.object(ext, 'tg_send', return_value=True) as send:
            r = self.client.post(reverse('telegram_webhook', args=['s3cret']), body, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        send.assert_called_once()
        self.assertEqual(self.client.get(reverse('telegram_webhook', args=['s3cret'])).status_code, 405)

    @override_settings(TELEGRAM_WEBHOOK_SECRET='')
    def test_webhook_disabled_without_secret(self):
        self.assertEqual(self.client.post(reverse('telegram_webhook', args=['']) if False else '/telegram/webhook/x/', '{}',
                                          content_type='application/json').status_code, 404)

    def test_disconnect_clears_everything(self):
        us = UserSettings.for_user(self.user)
        us.telegram_chat_id, us.reminders_enabled = '7', True
        us.save()
        self.client.post(reverse('telegram_disconnect'))
        us.refresh_from_db()
        self.assertEqual((us.telegram_chat_id, us.reminders_enabled), ('', False))


class ReminderTests(BaseCase):
    def make(self, times='08:00,13:00', chat='7', enabled=True):
        us = UserSettings.for_user(self.user)
        us.reminder_times, us.telegram_chat_id, us.reminders_enabled = times, chat, enabled
        us.save()
        return us

    def at(self, hh, mm):
        local = timezone.localtime(timezone.now()).replace(hour=hh, minute=mm, second=0, microsecond=0)
        return local

    def test_due_window_and_dedup(self):
        us = self.make()
        self.assertIsNone(ext.due_reminder_key(us, self.at(12, 59)))
        key = ext.due_reminder_key(us, self.at(13, 4))
        self.assertTrue(key.endswith('13:00'))
        self.assertIsNone(ext.due_reminder_key(us, self.at(13, 16)))             # window closed
        us.last_reminder_key = key
        self.assertIsNone(ext.due_reminder_key(us, self.at(13, 10)))             # already sent

    def test_bad_times_are_ignored(self):
        us = self.make(times='nope,25:99,13:00')
        self.assertIsNotNone(ext.due_reminder_key(us, self.at(13, 1)))

    @override_settings(TELEGRAM_BOT_TOKEN='123:ABC')
    def test_command_sends_once_per_slot(self):
        us = self.make(times=timezone.localtime(timezone.now()).strftime('%H:%M'))
        with mock.patch('tracker.management.commands.send_reminders.tg_send', return_value=True) as send:
            call_command('send_reminders', stdout=io.StringIO())
            call_command('send_reminders', stdout=io.StringIO())
        self.assertEqual(send.call_count, 1)
        self.assertIn('Time to log your meal', send.call_args.args[1])

    @override_settings(TELEGRAM_BOT_TOKEN='123:ABC')
    def test_command_skips_disabled_and_unlinked(self):
        self.make(times=timezone.localtime(timezone.now()).strftime('%H:%M'), enabled=False)
        with mock.patch('tracker.management.commands.send_reminders.tg_send', return_value=True) as send:
            call_command('send_reminders', stdout=io.StringIO())
        send.assert_not_called()


class NotificationAndEmailTests(BaseCase):
    def test_save_notification_settings(self):
        r = self.client.post(reverse('update_notifications'), {'weekly_email': 'on', 'reminder_times': '7:30, 12:00'})
        us = UserSettings.objects.get(user=self.user)
        self.assertEqual(us.reminder_times, '07:30,12:00')
        self.assertTrue(us.weekly_email)
        self.assertFalse(us.reminders_enabled)                                    # no Telegram yet

    def test_invalid_times_rejected(self):
        for bad in ('25:00', 'noon', '', '08:00,09:00,10:00,11:00,12:00,13:00,14:00'):
            self.client.post(reverse('update_notifications'), {'reminder_times': bad})
        self.assertEqual(UserSettings.for_user(self.user).reminder_times, '08:00,13:00,19:30')

    def test_reminders_require_telegram(self):
        r = self.client.post(reverse('update_notifications'), {'reminders_enabled': 'on', 'reminder_times': '08:00'}, follow=True)
        self.assertContains(r, 'Connect Telegram first')
        self.assertFalse(UserSettings.for_user(self.user).reminders_enabled)

    def test_email_save_validation_and_test_send(self):
        self.client.post(reverse('update_email'), {'email': 'not-an-email'})
        self.assertEqual(User_email(self.user), '')
        self.client.post(reverse('update_email'), {'email': 'me@example.com'})
        self.assertEqual(User_email(self.user), 'me@example.com')
        r = self.client.post(reverse('send_test_email'), follow=True)
        self.assertContains(r, 'Test email sent')
        self.assertEqual(mail.outbox[-1].to, ['me@example.com'])

    def test_test_email_needs_address_and_reports_smtp_failure(self):
        self.assertContains(self.client.post(reverse('send_test_email'), follow=True), 'Save an email address first')
        self.user.email = 'me@example.com'
        self.user.save()
        with mock.patch('tracker.views_integrations.send_mail', side_effect=OSError('connection refused')):
            r = self.client.post(reverse('send_test_email'), follow=True)
        self.assertContains(r, 'Could not send email')

    def test_weekly_summary_respects_opt_out(self):
        self.user.email = 'me@example.com'
        self.user.save()
        MealEntry.objects.create(user=self.user, food=self.food, quantity_grams=100, meal_type='lunch', date=timezone.localdate())
        us = UserSettings.for_user(self.user)
        us.weekly_email = False
        us.save()
        call_command('send_weekly_summary', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 0)
        us.weekly_email = True
        us.save()
        call_command('send_weekly_summary', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 1)

    def test_pages_render_without_any_keys(self):
        for name in ('connections', 'recipes'):
            with mock.patch.object(ext, 'http_json', side_effect=ext.ApiError('offline')):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertContains(self.client.get(reverse('connections')), 'Not set up yet')

    def test_connections_require_login(self):
        self.client.logout()
        for name in ('connections', 'recipes'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)


def User_email(user):
    user.refresh_from_db()
    return user.email
