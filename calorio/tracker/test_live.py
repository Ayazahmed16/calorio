from datetime import timedelta

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .models import Activity, Challenge
from .routing import websocket_urlpatterns

application = URLRouter(websocket_urlpatterns)


class LiveLeaderboardTests(TransactionTestCase):
    def setUp(self):
        self.member = User.objects.create_user('m', password='pass12345')
        self.outsider = User.objects.create_user('o', password='pass12345')
        today = timezone.localdate()
        self.challenge = Challenge.objects.create(
            name='T', metric='steps', creator=self.member,
            start_date=today, end_date=today + timedelta(days=6),
        )
        self.challenge.members.add(self.member)
        self.member_token = Token.objects.create(user=self.member).key
        self.outsider_token = Token.objects.create(user=self.outsider).key

    async def login(self, token):
        comm = WebsocketCommunicator(application, f'/ws/challenges/{self.challenge.id}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)
        await comm.send_json_to({'token': token})
        return comm

    async def test_member_gets_ready(self):
        comm = await self.login(self.member_token)
        self.assertEqual(await comm.receive_json_from(), {'type': 'ready'})
        await comm.disconnect()

    async def test_outsider_is_rejected(self):
        comm = await self.login(self.outsider_token)
        output = await comm.receive_output()
        self.assertEqual(output['type'], 'websocket.close')

    async def test_bad_token_is_rejected(self):
        comm = await self.login('not-a-real-token')
        output = await comm.receive_output()
        self.assertEqual(output['type'], 'websocket.close')

    async def test_new_steps_push_a_refresh(self):
        comm = await self.login(self.member_token)
        await comm.receive_json_from()  # the 'ready' message
        await sync_to_async(Activity.objects.create)(
            user=self.member, date=timezone.localdate(), steps=500
        )
        self.assertEqual(await comm.receive_json_from(), {'type': 'refresh'})
        await comm.disconnect()