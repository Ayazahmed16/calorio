from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Activity, Challenge, Meal


class ChallengeTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user('a', password='pass12345')
        self.b = User.objects.create_user('b', password='pass12345')
        self.c = User.objects.create_user('c', password='pass12345')
        self.today = timezone.localdate()
        self.client = APIClient()
        self.client.force_authenticate(user=self.a)

    def make(self, metric='steps'):
        challenge = Challenge.objects.create(
            name='T', metric=metric, creator=self.a,
            start_date=self.today, end_date=self.today + timedelta(days=6),
        )
        challenge.members.add(self.a, self.b)
        return challenge

    def board(self, challenge):
        response = self.client.get(f'/api/challenges/{challenge.id}/')
        return response.data['leaderboard']

    def test_create_adds_creator_and_invite_code(self):
        response = self.client.post('/api/challenges/', {
            'name': 'Steps week', 'metric': 'steps',
            'start_date': str(self.today),
            'end_date': str(self.today + timedelta(days=6)),
        }, format='json')
        self.assertEqual(response.status_code, 201)
        challenge = Challenge.objects.get(pk=response.data['id'])
        self.assertTrue(challenge.members.filter(pk=self.a.pk).exists())
        self.assertTrue(challenge.invite_code)

    def test_end_before_start_is_rejected(self):
        response = self.client.post('/api/challenges/', {
            'name': 'Bad', 'metric': 'steps',
            'start_date': str(self.today),
            'end_date': str(self.today - timedelta(days=1)),
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_non_member_cannot_see_challenge(self):
        challenge = self.make()
        self.client.force_authenticate(user=self.c)
        response = self.client.get(f'/api/challenges/{challenge.id}/')
        self.assertEqual(response.status_code, 404)

    def test_join_with_invite_code(self):
        challenge = self.make()
        self.client.force_authenticate(user=self.c)
        response = self.client.post(
            '/api/challenges/join/', {'code': challenge.invite_code}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(challenge.members.filter(pk=self.c.pk).exists())

    def test_bad_invite_code(self):
        response = self.client.post('/api/challenges/join/', {'code': 'nope'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_steps_leaderboard_ranks_and_ignores_other_dates(self):
        challenge = self.make()
        Activity.objects.create(user=self.a, date=self.today, steps=5000)
        Activity.objects.create(user=self.a, date=self.today - timedelta(days=1), steps=9000)  # before start
        Activity.objects.create(user=self.b, date=self.today, steps=8000)
        Activity.objects.create(user=self.c, date=self.today, steps=99999)  # not a member
        rows = [(r['username'], r['score'], r['rank']) for r in self.board(challenge)]
        self.assertEqual(rows, [('b', 8000, 1), ('a', 5000, 2)])

    def test_ties_share_a_rank(self):
        challenge = self.make()
        Activity.objects.create(user=self.a, date=self.today, steps=5000)
        Activity.objects.create(user=self.b, date=self.today, steps=5000)
        self.assertEqual([r['rank'] for r in self.board(challenge)], [1, 1])

    def test_protein_ignores_meals_before_start(self):
        challenge = self.make('protein')
        Meal.objects.create(user=self.a, name='x', calories=100, protein=30)
        old = Meal.objects.create(user=self.a, name='y', calories=100, protein=50)
        Meal.objects.filter(pk=old.pk).update(eaten_at=timezone.now() - timedelta(days=3))
        row = next(r for r in self.board(challenge) if r['username'] == 'a')
        self.assertEqual(row['score'], 30)