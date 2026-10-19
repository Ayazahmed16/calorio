from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from tracker.services import weekly_summary


class Command(BaseCommand):
    help = 'Email each user with an email address a summary of their last 7 days. Schedule it weekly (cron / Task Scheduler).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print instead of sending')

    def handle(self, *args, **opts):
        sent = 0
        for user in User.objects.filter(is_active=True).exclude(email='').exclude(settings__weekly_email=False):
            s = weekly_summary(user)
            if not s['days_logged']:
                continue          # nothing logged this week: stay quiet
            lines = [
                f'Hi {user.username}, here is your week ({s["start"]} to {s["end"]}):',
                '',
                f'- Days logged: {s["days_logged"]} of 7 (current streak: {s["streak"]})',
                f'- Average calories: {s["avg_calories"]} (goal {s["goal_calories"]}), on target {s["on_target"]} day(s)',
                f'- Average protein: {s["avg_protein"]} g',
                f'- Steps: {s["total_steps"]}, calories burned: {s["total_burned"]}',
            ]
            if s['weight_change'] is not None:
                lines.append(f'- Weight change: {s["weight_change"]:+g} kg')
            body = '\n'.join(lines)
            if opts['dry_run']:
                self.stdout.write(f'--- {user.email}\n{body}\n')
            else:
                send_mail('Your Calorio week', body, settings.DEFAULT_FROM_EMAIL, [user.email])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f'{sent} summary email(s) {"previewed" if opts["dry_run"] else "sent"}'))
