from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.integrations import day_summary_text, due_reminder_key, telegram_configured, tg_send
from tracker.models import UserSettings


class Command(BaseCommand):
    help = ('Send Telegram meal reminders that are due now. Run every 5-10 minutes '
            '(cron / Task Scheduler). Each reminder slot is sent at most once per day.')

    def handle(self, *args, **opts):
        if not telegram_configured():
            self.stdout.write('TELEGRAM_BOT_TOKEN is not set; nothing to do.')
            return
        now = timezone.now()
        sent = 0
        qs = UserSettings.objects.filter(reminders_enabled=True).exclude(telegram_chat_id='').select_related('user')
        for us in qs:
            key = due_reminder_key(us, now)
            if not key:
                continue
            us.last_reminder_key = key                 # mark handled first so a slow API call cannot double-send
            us.save(update_fields=['last_reminder_key'])
            text = 'Time to log your meal.\n\n' + day_summary_text(us.user)
            if tg_send(us.telegram_chat_id, text):
                sent += 1
        self.stdout.write(self.style.SUCCESS(f'{sent} reminder(s) sent'))
