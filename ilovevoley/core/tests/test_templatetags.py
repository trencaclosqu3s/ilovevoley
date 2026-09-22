from django.test import TestCase


class GetClubTeamFilterTest(TestCase):
    def test_returns_q_for_tenant_with_names(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.core.mixins import get_club_team_filter
        org = Organization.objects.create(
            slug='testclub',
            name='Test',
            club_team_names={'Senior': 'TEST CLUB', 'Juvenil': 'TEST B'},
        )
        q = get_club_team_filter(org)
        self.assertIsNotNone(q)

    def test_falls_back_to_settings_when_no_tenant(self):
        from ilovevoley.core.mixins import get_club_team_filter
        q = get_club_team_filter(None)
        self.assertIsNotNone(q)


class ClubTeamNamesTest(TestCase):
    def test_get_club_team_names_from_tenant(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.core.mixins import get_club_team_names, get_primary_club_team_name
        org = Organization.objects.create(
            slug='club',
            name='Club',
            club_team_names={'Senior': 'SANT JOSEP', 'Juvenil': 'SANT JOSEP B'},
        )
        self.assertEqual(get_club_team_names(org), ['SANT JOSEP', 'SANT JOSEP B'])
        self.assertEqual(get_primary_club_team_name(org), 'SANT JOSEP')

    def test_get_club_team_name_filter_matches_all_names(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.core.mixins import get_club_team_name_filter
        from ilovevoley.videos.models import Team, Category

        org = Organization.objects.create(
            slug='club',
            name='Club',
            club_team_names={'Senior': 'SANT JOSEP', 'Juvenil': 'SANT JOSEP B'},
        )
        category = Category.objects.create(name='Senior', is_active=True)
        Team.objects.create(name='CV SANT JOSEP', category=category, federation_id='fed-1')
        Team.objects.create(name='CV RIVAL', category=category, federation_id='fed-2')

        teams = Team.objects.filter(get_club_team_name_filter(org))
        self.assertEqual(teams.count(), 1)

    def test_blank_names_fall_back_to_settings(self):
        from django.test import override_settings
        from ilovevoley.core.models import Organization
        from ilovevoley.core.mixins import get_club_team_names

        org = Organization.objects.create(
            slug='blank-names', name='Blank', club_team_names={'Senior': ''},
        )
        with override_settings(CLUB_TEAM_NAME='FALLBACK'):
            self.assertEqual(get_club_team_names(org), ['FALLBACK'])
