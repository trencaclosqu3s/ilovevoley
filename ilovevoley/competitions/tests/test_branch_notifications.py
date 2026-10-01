from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchChangeLog
from ilovevoley.competitions.services.notifications import notify_match_changes
from ilovevoley.core.models import Category, GENDER_FEMALE, Organization, Season
from ilovevoley.rosters.models import Person, StaffRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

User = get_user_model()


class MatchBranchEmailFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        cls.club_a = Club.objects.create(federation_id='br-a', official_name='CV A')
        cls.club_b = Club.objects.create(federation_id='br-b', official_name='CV B')
        cls.org_a = Organization.objects.create(slug='br-a', name='Org A', club=cls.club_a)
        cls.org_b = Organization.objects.create(
            slug='br-b', name='Org B', club=cls.club_b,
            has_male_branch=False, has_female_branch=True,
        )
        cls.club_c = Club.objects.create(federation_id='br-c', official_name='CV C')
        cls.team_a = Team.objects.create(name='A F', federation_id='br-t-a', club=cls.club_a)
        cls.team_b = Team.objects.create(name='B F', federation_id='br-t-b', club=cls.club_b)
        cls.team_c = Team.objects.create(name='C F', federation_id='br-t-c', club=cls.club_c)
        cls.female = Category.objects.create(name='Senior Femenino Notif', gender=GENDER_FEMALE)
        cls.league = League.objects.create(name='Liga F', federation_id='br-l', season=cls.season, is_active=True)
        cls.league.categories.add(cls.female)
        cls.match = Match.objects.create(
            league=cls.league, home_team=cls.team_a, away_team=cls.team_b,
            match_date=timezone.now() + timedelta(days=2), venue='X',
        )
        person_a = Person.objects.create(
            first_name='Pep', last_name='A', email='a@example.com', organization=cls.org_a,
        )
        StaffRole.objects.create(
            person=person_a, team=cls.team_a, role='delegate', season=cls.season, is_active=True,
        )
        user_b = User.objects.create_user(username='mgrb', email='b@example.com')
        Membership.objects.create(user=user_b, organization=cls.org_b, role='manager', is_approved=True)
        person_c = Person.objects.create(
            first_name='Pep', last_name='C', email='c@example.com',
        )
        StaffRole.objects.create(
            person=person_c, team=cls.team_c, role='delegate', season=cls.season, is_active=True,
        )

    def _log(self, match=None):
        return MatchChangeLog.objects.create(
            match=match or self.match, change_type='venue', field_name='venue',
            old_value='A', new_value='B', is_last_minute=True,
        )

    def test_excludes_clubs_without_match_branch(self):
        with override_settings(MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True):
            sent = notify_match_changes([self._log()])

        self.assertEqual(sent, 1)
        email = mail.outbox[0]
        recipients = list(email.to) + list(email.bcc)
        self.assertNotIn('a@example.com', recipients)
        self.assertIn('b@example.com', recipients)

    def test_does_not_block_club_without_organization(self):
        match = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_c,
            match_date=timezone.now() + timedelta(days=2), venue='X',
        )
        with override_settings(MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True):
            sent = notify_match_changes([self._log(match)])

        self.assertEqual(sent, 1)
        email = mail.outbox[0]
        recipients = list(email.to) + list(email.bcc)
        self.assertIn('c@example.com', recipients)
