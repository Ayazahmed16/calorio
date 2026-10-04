import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notify_challenges(challenge_ids):
    layer = get_channel_layer()
    if layer is None:
        return
    for cid in challenge_ids:
        try:
            async_to_sync(layer.group_send)(f'challenge_{cid}', {'type': 'board.update'})
        except Exception:
            # a live-update problem must never stop a meal from being saved
            logging.exception('live update failed')