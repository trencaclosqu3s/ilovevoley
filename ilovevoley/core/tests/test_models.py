import datetime

from django.test import TestCase
from django.db import IntegrityError


class SeasonModelTest(TestCase):
    def test_normalize_season_name(self):
        from ilovevoley.core.models import normalize_season_name
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
        from ilovevoley.core.models import season_start_year_for_date
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 9, 20)), 2026)
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 8, 15)), 2025)
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 9, 1)), 2026)
        self.assertEqual(season_start_year_for_date(datetime.date(2026, 1, 3)), 2025)

    def test_resolve_creates_and_reuses_normalized_season(self):
        from ilovevoley.core.models import Season
        season = Season.objects.resolve('2025-2026')
        self.assertEqual(season.name, '2025-26')
        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.end_year, 2026)
        self.assertEqual(Season.objects.resolve('2025/26').pk, season.pk)
        self.assertEqual(Season.objects.resolve('temp'), None)
        self.assertEqual(Season.objects.count(), 1)

    def test_save_normalizes_name_and_derives_years(self):
        from ilovevoley.core.models import Season
        from django.core.exceptions import ValidationError
        season = Season.objects.create(name='2025/2026')
        self.assertEqual(season.name, '2025-26')
        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.end_year, 2026)
        with self.assertRaises(ValidationError):
            Season.objects.create(name='temp')

    def test_save_update_fields_persists_derived_values(self):
        from ilovevoley.core.models import Season
        season = Season.objects.create(name='2025-26')
        season.name = '2025/2026'
        season.is_current = True
        season.save(update_fields=['is_current'])
        season.refresh_from_db()
        self.assertEqual(season.name, '2025-26')
        self.assertEqual(season.start_year, 2025)
        self.assertEqual(season.end_year, 2026)

    def test_for_date_resolves_season(self):
        from ilovevoley.core.models import Season
        season = Season.objects.for_date(datetime.date(2026, 9, 20))
        self.assertEqual(season.name, '2026-27')

    def test_is_current_unique_constraint(self):
        from ilovevoley.core.models import Season
        Season.objects.create(name='2024-25', start_year=2024, end_year=2025, is_current=True)
        with self.assertRaises(IntegrityError):
            Season.objects.bulk_create([
                Season(name='2025-26', start_year=2025, end_year=2026, is_current=True),
            ])

    def test_save_current_unsets_previous(self):
        from ilovevoley.core.models import Season
        old = Season.objects.create(name='2024-25', start_year=2024, end_year=2025, is_current=True)
        new = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)
        new.is_current = True
        new.save()
        old.refresh_from_db()
        self.assertFalse(old.is_current)
        self.assertTrue(new.is_current)

    def test_current_auto_assigns_is_current_when_none_marked(self):
        from ilovevoley.core.models import Season
        Season.objects.create(name='2025-26', start_year=2025, end_year=2026)
        Season.objects.create(name='2026-27', start_year=2026, end_year=2027)
        # Estado inicial (como en producción): ninguna marcada como is_current
        self.assertEqual(Season.objects.filter(is_current=True).count(), 0)

        current = Season.objects.current(for_date=datetime.date(2026, 10, 8))
        self.assertEqual(current.name, '2026-27')
        self.assertTrue(current.is_current)
        self.assertEqual(Season.objects.filter(is_current=True).count(), 1)

    def test_future_season_from_scraping_does_not_displace_current(self):
        from ilovevoley.core.models import Season
        Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)

        # Simular scraping descubriendo la temporada 2027-28 en agosto de 2027
        future_season = Season.objects.resolve('2027-28')
        self.assertFalse(future_season.is_current)

        # En agosto de 2027, la temporada vigente sigue siendo 2026-27
        august_date = datetime.date(2027, 8, 15)
        current = Season.objects.current(for_date=august_date)
        self.assertEqual(current.name, '2026-27')
        self.assertEqual(Season.objects.filter(is_current=True).count(), 1)

    def test_season_rollover_on_september_cutoff(self):
        from ilovevoley.core.models import Season
        s2026 = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        s2027 = Season.objects.create(name='2027-28', start_year=2027, end_year=2028, is_current=False)

        # 31 de agosto de 2027: última jornada de la 2026-27
        self.assertEqual(
            Season.objects.current(for_date=datetime.date(2027, 8, 31)).pk,
            s2026.pk,
        )

        # 1 de septiembre de 2027: corte automático de temporada
        current = Season.objects.current(for_date=datetime.date(2027, 9, 1))
        self.assertEqual(current.pk, s2027.pk)
        s2026.refresh_from_db()
        s2027.refresh_from_db()
        self.assertFalse(s2026.is_current)
        self.assertTrue(s2027.is_current)
        self.assertEqual(Season.objects.filter(is_current=True).count(), 1)


class OrganizationModelTest(TestCase):
    def test_instagram_handle(self):
        from ilovevoley.core.models import Organization
        org = Organization.objects.create(
            slug='igclub',
            name='IG Club',
            instagram_url='https://www.instagram.com/clubvoleisantjosep/',
        )
        self.assertEqual(org.instagram_handle, '@clubvoleisantjosep')
        org.instagram_url = ''
        self.assertEqual(org.instagram_handle, '')

    def test_home_url_name_falls_back_when_unknown(self):
        from ilovevoley.core.models import Organization
        org = Organization.objects.create(
            slug='homeclub2', name='Home Club 2', default_home='nope'
        )
        self.assertEqual(org.home_url_name, 'content:video_list')


class OrganizationBranchesTest(TestCase):
    def test_default_branches_are_male_only(self):
        from ilovevoley.core.models import GENDER_MALE, Organization

        org = Organization.objects.create(slug='o-default', name='Org Default')
        self.assertEqual(org.active_branches, {GENDER_MALE})
