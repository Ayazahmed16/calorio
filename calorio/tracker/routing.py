from django.urls import path

from .consumers import ChallengeConsumer

websocket_urlpatterns = [
    path('ws/challenges/<int:challenge_id>/', ChallengeConsumer.as_asgi()),
]