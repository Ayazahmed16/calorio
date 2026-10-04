import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tracker.reports import send_weekly_report


class Command(BaseCommand):
    help = 'Email the weekly PDF report to users who turned it on.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List who would get an email, and send nothing.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.filter(
            is_active=True, reportpref__weekly_email=True
        ).exclude(email='')

        sent = failed = 0
        for user in users:
            if options['dry_run']:
                self.stdout.write(f'Would send to {user.username} <{user.email}>')
                continue
            try:
                send_weekly_report(user)
                sent += 1
            except Exception:
                # one bad address must not stop everyone else's report
                logging.exception('weekly report failed for user %s', user.pk)
                failed += 1

        if not options['dry_run']:
            self.stdout.write(f'Sent {sent}, failed {failed}.')