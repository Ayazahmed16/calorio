from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework.authtoken.models import Token

from .models import Challenge


class ChallengeConsumer(AsyncJsonWebsocketConsumer):
    group = None

    async def connect(self):
        await self.accept()

    async def receive_json(self, content, **kwargs):
        if self.group:
            return  # already logged in, nothing else is accepted

        token_key = str(content.get('token', '')) if isinstance(content, dict) else ''
        challenge_id = self.scope['url_route']['kwargs']['challenge_id']

        if not await self.is_member(token_key, challenge_id):
            await self.close(code=4403)
            return

        self.group = f'challenge_{challenge_id}'
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.send_json({'type': 'ready'})

    async def disconnect(self, code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    # called when the group gets {'type': 'board.update'}
    async def board_update(self, event):
        await self.send_json({'type': 'refresh'})

    @database_sync_to_async
    def is_member(self, token_key, challenge_id):
        if not token_key:
            return False
        try:
            user = Token.objects.select_related('user').get(key=token_key).user
        except Token.DoesNotExist:
            return False
        return (
            user.is_active
            and Challenge.objects.filter(pk=challenge_id, members=user).exists()
        )