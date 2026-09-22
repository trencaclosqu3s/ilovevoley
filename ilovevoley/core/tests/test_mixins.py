from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.core.mixins import get_club_team_filter, get_club_team_name_filter
from ilovevoley.core.models import Category, Organization
from ilovevoley.teams.models import Club, Team


class HybridClubFilterTest(TestCase):
    """Filtros que combinan la FK Club con el fallback por nombre."""

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Senior', is_active=True)
        cls.club = Club.objects.create(federation_id='club-1', official_name='CV SANT JOSEP')
        cls.other_club = Club.objects.create(federation_id='club-2', official_name='CV RIVAL')

        # Equipo del club con nombre que NO contiene club_team_names a propósito
        cls.fk_team = Team.objects.create(
            name='BAR BINI SOLLER', federation_id='team-1', club=cls.club,
        )
        # Equipo sin club pero cuyo nombre casa con club_team_names (dato histórico)
        cls.string_team = Team.objects.create(
            name='CV SANT JOSEP B', federation_id='team-2', club=None,
        )
        # Equipo ajeno, ni FK ni nombre
        cls.outside_team = Team.objects.create(
            name='CV ALTRES', federation_id='team-3', club=cls.other_club,
        )
        # Equipo de OTRO club cuyo nombre sí casa con club_team_names: no debe
        # colarse por el fallback de string
        cls.foreign_name_team = Team.objects.create(
            name='CV SANT JOSEP ALTRES', federation_id='team-4', club=cls.other_club,
        )

        cls.org = Organization.objects.create(
            slug='test-santjosep', name='Sant Josep',
            club=cls.club, club_team_names={'Senior': 'SANT JOSEP'},
        )

    def _matches_with(self, team, text=''):
        Match.objects.create(
            league=None, home_team=team, match_date=timezone.now(), home_team_text=text,
        )

    def test_match_filter_includes_team_by_club_fk(self):
        self._matches_with(self.fk_team)
        matches = Match.objects.filter(get_club_team_filter(self.org))
        self.assertEqual(matches.count(), 1)

    def test_match_filter_includes_team_without_club_by_name(self):
        self._matches_with(self.string_team)
        matches = Match.objects.filter(get_club_team_filter(self.org))
        self.assertEqual(matches.count(), 1)

    def test_match_filter_excludes_other_club(self):
        self._matches_with(self.outside_team)
        matches = Match.objects.filter(get_club_team_filter(self.org))
        self.assertEqual(matches.count(), 0)

    def test_name_fallback_does_not_leak_other_club_teams(self):
        self._matches_with(self.foreign_name_team)
        matches = Match.objects.filter(get_club_team_filter(self.org))
        self.assertEqual(matches.count(), 0)

    def test_text_fallback_matches_friendly_without_team(self):
        Match.objects.create(
            home_team=None, home_team_text='CV SANT JOSEP', match_date=timezone.now(),
        )
        self.assertEqual(Match.objects.filter(get_club_team_filter(self.org)).count(), 1)

    def test_text_fallback_does_not_leak_other_club_match(self):
        self._matches_with(self.foreign_name_team, text='CV SANT JOSEP')
        matches = Match.objects.filter(get_club_team_filter(self.org))
        self.assertEqual(matches.count(), 0)

    def test_team_filter_includes_all_club_teams_and_name_fallback(self):
        teams = Team.objects.filter(get_club_team_name_filter(self.org))
        self.assertCountEqual(
            teams.values_list('federation_id', flat=True),
            ['team-1', 'team-2'],
        )

    def test_tenant_without_club_only_uses_string_fallback(self):
        org = Organization.objects.create(
            slug='test-balears', name='Selecció Balear',
            club=None, club_team_names={'Senior': 'BALEARS'},
        )
        Team.objects.create(name='SELECCIO BALEARS', federation_id='team-bal')
        self._matches_with(self.fk_team)  # club SANT JOSEP, no debe entrar

        names = list(
            Team.objects.filter(get_club_team_name_filter(org))
            .values_list('name', flat=True)
        )
        self.assertEqual(names, ['SELECCIO BALEARS'])
        self.assertEqual(Match.objects.filter(get_club_team_filter(org)).count(), 0)

    def test_blank_club_team_names_do_not_match_everything(self):
        from django.test import override_settings

        org = Organization.objects.create(
            slug='test-blank-names', name='Blank', club=None,
            club_team_names={'Senior': ''},
        )
        Team.objects.create(name='CV ALTRES', federation_id='team-blank')
        with override_settings(CLUB_TEAM_NAME='ZZZ'):
            names = list(
                Team.objects.filter(get_club_team_name_filter(org))
                .values_list('name', flat=True)
            )
        self.assertEqual(names, [])
