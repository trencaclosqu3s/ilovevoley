import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchShareLink
from ilovevoley.competitions.share import (
    create_match_share_link,
    group_match_media,
    resolve_match_share_link,
    revoke_match_share_link,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class MatchShareLinkTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='manager', password='pass')
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.home = Team.objects.create(name='Test Senior', category=self.category, club=self.club, federation_id='T1')
        self.away = Team.objects.create(name='Rival Senior', category=self.category, federation_id='T2')
        self.league = League.objects.create(
            name='Liga Test', federation_id='L1',
            season=Season.objects.resolve('2026-2027'), is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status='finished', home_score=3, away_score=1,
        )

    def test_create_sets_expiry_and_token(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        self.assertIsInstance(link.token, uuid.UUID)
        delta = link.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(hours=47, minutes=55))
        self.assertLessEqual(delta, timedelta(hours=48))
        self.assertTrue(link.is_active)

    def test_create_clamps_hours_to_max(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=10_000)
        self.assertLessEqual(link.expires_at - timezone.now(), timedelta(hours=720, minutes=1))

    def test_resolve_returns_active_link_and_none_when_expired(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        self.assertEqual(resolve_match_share_link(link.token), link)

        MatchShareLink.objects.filter(pk=link.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertIsNone(resolve_match_share_link(link.token))

    def test_resolve_returns_none_when_revoked(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        revoke_match_share_link(link)
        link.refresh_from_db()
        self.assertIsNotNone(link.revoked_at)
        self.assertIsNone(resolve_match_share_link(link.token))

    def test_resolve_unknown_token_returns_none(self):
        self.assertIsNone(resolve_match_share_link(uuid.uuid4()))

    def test_group_match_media_orders_sets_and_appends_ungrouped(self):
        groups = group_match_media(
            videos=[],
            images=[
                {'set_number': None, 'title': 'sin'},
                {'set_number': 2, 'title': 'dos'},
                {'set_number': 1, 'title': 'uno'},
            ],
            set_labels={1: 'Primer set'},
        )
        self.assertEqual([g['set_number'] for g in groups], [1, 2, None])
        self.assertEqual(groups[0]['label'], 'Primer set')
        self.assertEqual(groups[1]['label'], 'Set 2')
        self.assertEqual(groups[2]['label'], 'Sin set')
        self.assertEqual(groups[0]['images'], [{'set_number': 1, 'title': 'uno'}])
