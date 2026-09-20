import datetime

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError


class SeasonModelTest(TestCase):
    def test_normalize_season_name(self):
        from videosvoley.core.models import normalize_season_name
        self.assertEqual(normalize_season_name('2025-26'), '2025-26')
        self.assertEqual(normalize_season_name('2025-2026'), '2025-26')
        self.assertEqual(normalize_season_name('2025/26'), '2025-26')
        self.assertEqual(normalize_season_name('1999-2000'), '1999-00')
        self.assertIsNone(normalize_season_name('2025-27'))
        self.assertIsNone(normalize_season_name('temp'))
        self.assertIsNone(normalize_season_name(''))
        self.assertIsNone(normalize_season_name(None))
        self.assertIsNone(normalize_season_name('2025'))

    def test_season_start_year_for_date_uses_september_cutoff(self):
        from videosvoley.core.models import season_start_year_for_date
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 9, 20)), 2026)
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 8, 15)), 2025)
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 9, 1)), 2026)
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 1, 3)), 2025)

    def test_resolve_creates_and_reuses_normalized_season(self):
        from videosvoley.core.models import Season
        season = Season.objects.resolve('2025-2026')
        self.assertEqual(season.name, '2025-26')
        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.end_year, 2026)
        self.assertEqual(Season.objects.resolve('2025/26').pk, season.pk)
        self.assertEqual(Season.objects.resolve('temp'), None)
        self.assertEqual(Season.objects.count(), 1)

    def test_save_normalizes_name_and_derives_years(self):
        from videosvoley.core.models import Season
        from django.core.exceptions import ValidationError
        season = Season.objects.create(name='2025/2026')
        self.assertEqual(season.name, '2025-26')
        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.end_year, 2026)
        with self.assertRaises(ValidationError):
            Season.objects.create(name='temp')

    def test_save_update_fields_persists_derived_values(self):
        from videosvoley.core.models import Season
        season = Season.objects.create(name='2025-26')
        season.name = '2025/2026'
        season.is_current = True
        season.save(update_fields=['is_current'])
        season.refresh_from_db()
        self.assertEqual(season.name, '2025-26')
        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.end_year, 2026)

    def test_for_date_resolves_season(self):
        from videosvoley.core.models import Season
        season = Season.objects.for_date(datetime.date(2026, 9, 20))
        self.assertEqual(season.name, '2026-27')

    def test_is_current_unique_constraint(self):
        from videosvoley.core.models import Season
        Season.objects.create(name='2024-25', start_year=2024, end_year=2025, is_current=True)
        with self.assertRaises(IntegrityError):
            Season.objects.bulk_create([
                Season(name='2025-26', start_year=2025, end_year=2026, is_current=True),
            ])

    def test_save_current_unsets_previous(self):
        from videosvoley.core.models import Season
        old = Season.objects.create(name='2024-25', start_year=2024, end_year=2025, is_current=True)
        new = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)
        new.is_current = True
        new.save()
        old.refresh_from_db()
        self.assertFalse(old.is_current)
        self.assertTrue(new.is_current)

    def test_current_falls_back_to_latest(self):
        from videosvoley.core.models import Season
        Season.objects.create(name='2023-24', start_year=2023, end_year=2024)
        Season.objects.create(name='2024-25', start_year=2024, end_year=2025)
        self.assertEqual(Season.objects.current().name, '2024-25')


class OrganizationModelTest(TestCase):
    def test_create_organization(self):
        from videosvoley.core.models import Organization
        org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            primary_color='#ff0000',
            club_team_names={'Senior': 'TEST CLUB'},
        )
        self.assertEqual(org.slug, 'testclub')
        self.assertEqual(org.club_team_names['Senior'], 'TEST CLUB')
        self.assertTrue(org.is_active)

    def test_slug_unique(self):
        from videosvoley.core.models import Organization
        from django.db import IntegrityError
        Organization.objects.create(slug='unique', name='A')
        with self.assertRaises(IntegrityError):
            Organization.objects.create(slug='unique', name='B')

    def test_instagram_handle(self):
        from videosvoley.core.models import Organization
        org = Organization.objects.create(
            slug='igclub',
            name='IG Club',
            instagram_url='https://www.instagram.com/clubvoleisantjosep/',
        )
        self.assertEqual(org.instagram_handle, '@clubvoleisantjosep')
        org.instagram_url = ''
        self.assertEqual(org.instagram_handle, '')


class MembershipModelTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        User = get_user_model()
        self.org = Organization.objects.create(slug='club1', name='Club 1')
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_create_membership(self):
        from videosvoley.users.models import Membership
        m = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role='member',
            is_approved=False,
        )
        self.assertEqual(m.role, 'member')
        self.assertFalse(m.is_approved)

    def test_unique_user_organization(self):
        from videosvoley.users.models import Membership
        from django.db import IntegrityError
        Membership.objects.create(user=self.user, organization=self.org)
        with self.assertRaises(IntegrityError):
            Membership.objects.create(user=self.user, organization=self.org)
