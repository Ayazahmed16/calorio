from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .gamification import BADGES, award_badges, compute_stats
from .models import Badge


class StreakView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stats = compute_stats(request.user)
        award_badges(request.user, stats)  # also catches up on older data
        earned = {b.code: b.awarded_at for b in Badge.objects.filter(user=request.user)}
        return Response({
            'streaks': {key: stats[key] for key in ('logging', 'protein', 'steps')},
            'badges': [
                {
                    'code': code,
                    'name': name,
                    'description': desc,
                    'earned': code in earned,
                    'awarded_at': earned.get(code),
                }
                for code, (name, desc, _) in BADGES.items()
            ],
        })