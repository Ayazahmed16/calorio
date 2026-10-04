from django.db.models import Count, FloatField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Challenge

MAX_MEMBERS = 30
MAX_DAYS = 90
MAX_CREATED = 20


class ChallengeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Challenge
        fields = ['name', 'metric', 'start_date', 'end_date']

    def validate(self, data):
        start, end = data['start_date'], data['end_date']
        if end < start:
            raise serializers.ValidationError('End date must not be before the start date.')
        if (end - start).days > MAX_DAYS:
            raise serializers.ValidationError(f'A challenge can last at most {MAX_DAYS} days.')
        return data


def status_of(challenge, today):
    if today < challenge.start_date:
        return 'upcoming'
    if today > challenge.end_date:
        return 'ended'
    return 'active'


def challenge_data(challenge, today):
    return {
        'id': challenge.id,
        'name': challenge.name,
        'metric': challenge.metric,
        'start_date': challenge.start_date,
        'end_date': challenge.end_date,
        'status': status_of(challenge, today),
        'members': challenge.members.count(),
    }


def leaderboard(challenge):
    start, end = challenge.start_date, challenge.end_date

    # each metric joins only ONE related table, so the sums are never double counted
    if challenge.metric == 'steps':
        score = Coalesce(
            Sum('activity__steps', filter=Q(activity__date__gte=start, activity__date__lte=end)),
            0,
        )
    elif challenge.metric == 'protein':
        score = Coalesce(
            Sum('meal__protein', filter=Q(meal__eaten_at__date__gte=start, meal__eaten_at__date__lte=end)),
            Value(0.0),
            output_field=FloatField(),
        )
    else:
        score = Count(
            TruncDate('meal__eaten_at'),
            filter=Q(meal__eaten_at__date__gte=start, meal__eaten_at__date__lte=end),
            distinct=True,
        )

    rows = list(
        challenge.members.annotate(score=score)
        .order_by('-score', 'username')
        .values('id', 'username', 'score')
    )

    # same score = same rank (1, 1, 3)
    rank, previous = 0, None
    for position, row in enumerate(rows, start=1):
        if challenge.metric == 'protein':
            row['score'] = round(float(row['score']), 1)
        if row['score'] != previous:
            rank, previous = position, row['score']
        row['rank'] = rank
    return rows


class ChallengeListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        challenges = request.user.challenges.order_by('-start_date')[:50]
        return Response([challenge_data(c, today) for c in challenges])

    def post(self, request):
        serializer = ChallengeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if request.user.created_challenges.count() >= MAX_CREATED:
            return Response({'detail': 'You have created too many challenges.'}, status=400)
        challenge = serializer.save(creator=request.user)
        challenge.members.add(request.user)
        return Response(challenge_data(challenge, timezone.localdate()), status=201)


class ChallengeDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        # members only. Everyone else gets a 404, so nobody can tell it exists.
        challenge = get_object_or_404(Challenge.objects.filter(members=request.user), pk=pk)
        data = challenge_data(challenge, timezone.localdate())
        data['invite_code'] = challenge.invite_code
        data['me'] = request.user.username
        data['leaderboard'] = leaderboard(challenge)
        return Response(data)


class JoinView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'join'

    def post(self, request):
        today = timezone.localdate()
        code = str(request.data.get('code', '')).strip()[:40]
        challenge = Challenge.objects.filter(invite_code=code).first() if code else None
        if not challenge:
            return Response({'detail': 'Invalid invite code.'}, status=404)

        if challenge.members.filter(pk=request.user.pk).exists():
            return Response(challenge_data(challenge, today))
        if challenge.end_date < today:
            return Response({'detail': 'This challenge has ended.'}, status=400)
        if challenge.members.count() >= MAX_MEMBERS:
            return Response({'detail': 'This challenge is full.'}, status=400)

        challenge.members.add(request.user)
        return Response(challenge_data(challenge, today))


class LeaveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        challenge = get_object_or_404(Challenge.objects.filter(members=request.user), pk=pk)
        challenge.members.remove(request.user)
        if not challenge.members.exists():
            challenge.delete()
        return Response(status=204)