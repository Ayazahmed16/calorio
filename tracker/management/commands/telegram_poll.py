import time

from django.conf import settings
from django.core.management.base import BaseCommand

from tracker.integrations import ApiError, telegram_configured, tg_api, tg_handle_update


class Command(BaseCommand):
    help = ('Receive Telegram messages by long polling. Use this on a laptop/dev machine instead of a webhook: '
            'it lets users link their account (/start CODE) and use /today and /water.')

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process pending updates once and exit')

    def handle(self, *args, **opts):
        if not telegram_configured():
            self.stderr.write('Set TELEGRAM_BOT_TOKEN first.')
            return
        try:
            tg_api('deleteWebhook', {})          # polling and webhooks are mutually exclusive
        except ApiError:
            pass
        offset = None
        self.stdout.write('Polling Telegram... (Ctrl+C to stop)')
        while True:
            try:
                payload = {'timeout': 0 if opts['once'] else 25, 'allowed_updates': ['message']}
                if offset:
                    payload['offset'] = offset
                updates = tg_api('getUpdates', payload).get('result', [])
            except ApiError as e:
                self.stderr.write(f'poll error: {e}')
                time.sleep(5)
                continue
            for u in updates:
                offset = u['update_id'] + 1
                tg_handle_update(u)
            if opts['once']:
                self.stdout.write(f'{len(updates)} update(s) processed')
                return
