from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Activity, Meal, ReportPref
from .reports import build_pdf, week_data


class ReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('a', password='pass12345', email='a@example.com')
        self.other = User.objects.create_user('b', password='pass12345')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_week_data_totals(self):
        Meal.objects.create(user=self.user, name='x', calories=500, protein=30)
        Meal.objects.create(user=self.user, name='y', calories=300, protein=20)
        Meal.objects.create(user=self.other, name='z', calories=9999, protein=99)  # other user
        old = Meal.objects.create(user=self.user, name='old', calories=7777, protein=77)
        Meal.objects.filter(pk=old.pk).update(eaten_at=timezone.now() - timedelta(days=10))
        Activity.objects.create(user=self.user, date=timezone.localdate(), steps=4000)

        data = week_data(self.user)
        self.assertEqual(data['days_logged'], 1)
        self.assertEqual(data['avg_calories'], 800)
        self.assertEqual(data['total_steps'], 4000)

    def test_pdf_is_valid_and_survives_odd_username(self):
        weird = User.objects.create_user('a<b>&c', password='pass12345')
        pdf = build_pdf(weird, week_data(weird))
        self.assertTrue(pdf.startswith(b'%PDF'))

    def test_download_endpoint_returns_pdf(self):
        response = self.client.get('/api/report/weekly/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_download_requires_login(self):
        response = APIClient().get('/api/report/weekly/')
        self.assertIn(response.status_code, [401, 403])

    def test_command_emails_only_opted_in_users_with_email(self):
        ReportPref.objects.create(user=self.user, weekly_email=True)
        no_email = User.objects.create_user('c', password='pass12345')
        ReportPref.objects.create(user=no_email, weekly_email=True)  # opted in, no address
        self.other.email = 'b@example.com'
        self.other.save()
        ReportPref.objects.create(user=self.other, weekly_email=False)  # has address, not opted in

        call_command('send_weekly_reports')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['a@example.com'])
        filename, content, mimetype = mail.outbox[0].attachments[0]
        self.assertTrue(filename.endswith('.pdf'))
        self.assertEqual(mimetype, 'application/pdf')

    def test_dry_run_sends_nothing(self):
        ReportPref.objects.create(user=self.user, weekly_email=True)
        call_command('send_weekly_reports', '--dry-run')
        self.assertEqual(len(mail.outbox), 0)

    def test_settings_roundtrip(self):
        response = self.client.put(
            '/api/report/settings/',
            {'email': 'new@example.com', 'weekly_email': True},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertTrue(ReportPref.objects.get(user=self.user).weekly_email)

    def test_weekly_email_needs_an_address(self):
        response = self.client.put(
            '/api/report/settings/', {'email': '', 'weekly_email': True}, format='json'
        )
        self.assertEqual(response.status_code, 400)