from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchLineup
from ilovevoley.competitions.services.lineups import (
    build_match_lineups,
    get_player_season_stats,
    store_match_lineups,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team


def _entry(position, number, sub=None):
    return {'position': position, 'number': number, 'sub': sub}


def _six(start=1):
    return [_entry(pos, start + i) for i, pos in enumerate(('I', 'II', 'III', 'IV', 'V', 'VI'))]


def _set(title, home_lineup, away_lineup):
    return {
        'title': title,
        'time': '',
        'teams': [
            {'name': 'Test Club Senior', 'points': 25, 'lineup': home_lineup},
            {'name': 'Rival Team Senior', 'points': 20, 'lineup': away_lineup},
        ],
    }


def _lineup_data(home_convocados, sets):
    return {
        'home_team': 'Test Club Senior',
        'away_team': 'Rival Team Senior',
        'home_captain': '',
        'away_captain': '',
        'home_convocados': home_convocados,
        'away_convocados': [],
        'sets': sets,
    }


class MatchLineupBuildingTests(TestCase):
    """El recuento por jugador es la base del histórico: un error aquí lo corrompe."""

    def setUp(self):
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club,
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category,
            club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival Team Senior', category=self.category,
            club=Club.objects.create(official_name='Rival', federation_id='CLUB-R'),
            federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Superliga 2', federation_id='LEAGUE-T', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
        )

    def test_sets_played_cuenta_titulares_y_suplentes(self):
        # #1, #2 y #3 empiezan los dos sets; #9 entra por #2 en el set 1.
        data = _lineup_data(
            home_convocados=['1 Uno', '2 Dos', '3 Tres', '9 Nueve', '10 Diez'],
            sets=[
                _set('Set 1', [_entry('I', 1), _entry('II', 2, {'number': 9, 'score': '(5-6)'}),
                               _entry('III', 3), _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11)),
                _set('Set 2', [_entry('I', 1), _entry('II', 2), _entry('III', 3),
                               _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11)),
            ],
        )
        rows = {r.jersey_number: r for r in build_match_lineups(self.match, data)}

        self.assertEqual(rows[1].sets_played, 2)
        self.assertEqual(rows[1].sets_started, 2)
        self.assertTrue(rows[1].is_convocado)

        # El suplente juega el set en que entra, pero no es titular.
        self.assertEqual(rows[9].sets_played, 1)
        self.assertEqual(rows[9].sets_started, 0)

        # Un convocado que no aparece en ningún set no juega.
        self.assertEqual(rows[10].sets_played, 0)
        self.assertTrue(rows[10].is_convocado)

        # Un dorsal que juega sin figurar entre los convocados también se registra.
        self.assertEqual(rows[4].sets_played, 2)
        self.assertFalse(rows[4].is_convocado)

    def test_person_se_resuelve_por_dorsal_y_temporada(self):
        person = Person.objects.create(first_name='Ana', last_name='Ruiz', organization=self.org)
        PlayerRole.objects.create(
            person=person, team=self.team, season=self.season,
            jersey_number=7, is_active=True,
        )
        data = _lineup_data(
            home_convocados=['7 Ruiz'],
            sets=[_set('Set 1', [_entry('I', 7), _entry('II', 2), _entry('III', 3),
                                 _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11))],
        )

        rows = {r.jersey_number: r for r in build_match_lineups(self.match, data)}
        self.assertEqual(rows[7].person_id, person.id)

    def test_person_se_resuelve_aunque_el_rol_este_inactivo(self):
        person = Person.objects.create(first_name='Baja', last_name='Temporada', organization=self.org)
        PlayerRole.objects.create(
            person=person, team=self.team, season=self.season,
            jersey_number=7, is_active=False,
        )
        data = _lineup_data(
            home_convocados=['7 Dorsal'],
            sets=[_set('Set 1', [_entry('I', 7), _entry('II', 2), _entry('III', 3),
                                 _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11))],
        )

        rows = {r.jersey_number: r for r in build_match_lineups(self.match, data)}
        self.assertEqual(rows[7].person_id, person.id)

    def test_rol_activo_gana_ante_dorsal_repetido(self):
        # El activo se crea primero (id menor) para que el test no pase por azar
        # de orden: la precedencia debe decidirla is_active, no el id.
        activo = Person.objects.create(first_name='Activa', last_name='Dos', organization=self.org)
        inactivo = Person.objects.create(first_name='Baja', last_name='Uno', organization=self.org)
        PlayerRole.objects.create(
            person=activo, team=self.team, season=self.season,
            jersey_number=7, is_active=True,
        )
        PlayerRole.objects.create(
            person=inactivo, team=self.team, season=self.season,
            jersey_number=7, is_active=False,
        )
        data = _lineup_data(
            home_convocados=['7 Dorsal'],
            sets=[_set('Set 1', [_entry('I', 7), _entry('II', 2), _entry('III', 3),
                                 _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11))],
        )

        rows = {r.jersey_number: r for r in build_match_lineups(self.match, data)}
        self.assertEqual(rows[7].person_id, activo.id)

    def test_entre_dorsal_repetido_gana_el_rol_mas_reciente(self):
        antiguo = Person.objects.create(first_name='Antigua', last_name='Dorsal', organization=self.org)
        reciente = Person.objects.create(first_name='Reciente', last_name='Dorsal', organization=self.org)
        PlayerRole.objects.create(
            person=antiguo, team=self.team, season=self.season,
            jersey_number=7, is_active=False,
        )
        PlayerRole.objects.create(
            person=reciente, team=self.team, season=self.season,
            jersey_number=7, is_active=False,
        )
        data = _lineup_data(
            home_convocados=['7 Dorsal'],
            sets=[_set('Set 1', [_entry('I', 7), _entry('II', 2), _entry('III', 3),
                                 _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11))],
        )

        rows = {r.jersey_number: r for r in build_match_lineups(self.match, data)}
        self.assertEqual(rows[7].person_id, reciente.id)

    def test_no_mezcla_dorsal_de_otra_temporada(self):
        otro = Season.objects.resolve('2024-25')
        person = Person.objects.create(first_name='Vieja', last_name='Dorsal', organization=self.org)
        PlayerRole.objects.create(
            person=person, team=self.team, season=otro,
            jersey_number=7, is_active=True,
        )
        data = _lineup_data(
            home_convocados=['7 Dorsal'],
            sets=[_set('Set 1', [_entry('I', 7), _entry('II', 2), _entry('III', 3),
                                 _entry('IV', 4), _entry('V', 5), _entry('VI', 6)], _six(11))],
        )

        rows = {r.jersey_number: r for r in build_match_lineups(self.match, data)}
        self.assertIsNone(rows[7].person_id)

    def test_store_es_idempotente(self):
        data = _lineup_data(
            home_convocados=['1 Uno'],
            sets=[_set('Set 1', _six(1), _six(11))],
        )
        store_match_lineups(self.match, data)
        primer_conteo = MatchLineup.objects.filter(match=self.match).count()
        store_match_lineups(self.match, data)

        self.assertEqual(MatchLineup.objects.filter(match=self.match).count(), primer_conteo)
        self.match.refresh_from_db()
        self.assertEqual(self.match.acta_data['home_convocados'], ['1 Uno'])


class PlayerSeasonStatsTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category,
            club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival Senior', category=self.category, federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Liga', federation_id='L-1', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.person = Person.objects.create(first_name='Ana', last_name='Ruiz', organization=self.org)

    def _match(self, season=None):
        liga = self.league
        if season is not None and season != self.season:
            liga = League.objects.create(
                name=f'Liga {season.name}', federation_id=f'L-{season.name}',
                season=season, is_active=True, visibility_type='main', is_our_team_related=True,
            )
        return Match.objects.create(
            league=liga, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
        )

    def _lineup(self, match, team, person, convocado=True, played=0, started=0):
        return MatchLineup.objects.create(
            match=match, team=team, person=person, jersey_number=7,
            is_convocado=convocado, sets_played=played, sets_started=started,
        )

    def test_agrega_por_temporada_y_excluye_otros_equipos(self):
        m1 = self._match()
        m2 = self._match()
        self._lineup(m1, self.team, self.person, convocado=True, played=3, started=3)
        self._lineup(m2, self.team, self.person, convocado=True, played=2, started=0)

        # Fila de otro club (mismo jugador, otro equipo) que no debe entrar en el ámbito del club.
        otro_equipo = Team.objects.create(
            name='Otro Club', category=self.category, federation_id='TEAM-3', is_active=True,
        )
        m3 = self._match()
        self._lineup(m3, otro_equipo, self.person, convocado=True, played=5, started=5)

        # Temporada distinta.
        otra = Season.objects.resolve('2024-25')
        m4 = self._match(season=otra)
        self._lineup(m4, self.team, self.person, convocado=True, played=4, started=4)

        stats = get_player_season_stats(self.person, self.season, [self.team])
        self.assertEqual(stats['convocatorias'], 2)
        self.assertEqual(stats['partidos_jugados'], 2)
        self.assertEqual(stats['titularidades'], 1)
        self.assertEqual(stats['sets_disputados'], 5)
        self.assertEqual(stats['sets_titular'], 3)

    def test_sin_temporada_agrega_todo(self):
        m1 = self._match()
        self._lineup(m1, self.team, self.person, played=3, started=3)
        otra = Season.objects.resolve('2024-25')
        m2 = self._match(season=otra)
        self._lineup(m2, self.team, self.person, played=2, started=2)

        stats = get_player_season_stats(self.person, None, [self.team])
        self.assertEqual(stats['sets_disputados'], 5)


@override_settings(ACTA_ALLOWED_HOSTS=['federacion.example'])
class BackfillActasCommandTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(slug='testclub', name='Test Club', club=self.club, is_active=True)
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(name='Test Club Senior', category=self.category, club=self.club, federation_id='TEAM-1')
        self.rival = Team.objects.create(name='Rival', category=self.category, federation_id='TEAM-2')
        self.league = League.objects.create(
            name='Liga', federation_id='L-1', season=Season.objects.resolve('2025-26'),
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
            acta_html='https://federacion.example/acta/1',
        )

    def test_backfill_persiste_actas_pendientes(self):
        data = _lineup_data(
            home_convocados=['1 Uno'],
            sets=[_set('Set 1', _six(1), _six(11))],
        )
        with patch('ilovevoley.competitions.management.commands.backfill_acta_lineups.safe_get',
                   return_value=b'<html></html>') as get, \
                patch('ilovevoley.competitions.management.commands.backfill_acta_lineups.parse_acta_lineup',
                      return_value=data):
            call_command('backfill_acta_lineups')

        get.assert_called_once()
        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.acta_data)
        self.assertTrue(MatchLineup.objects.filter(match=self.match).exists())

    def test_backfill_ignora_los_ya_procesados(self):
        self.match.acta_data = {'sets': []}
        self.match.save(update_fields=['acta_data'])
        with patch('ilovevoley.competitions.management.commands.backfill_acta_lineups.safe_get') as get:
            call_command('backfill_acta_lineups')
        get.assert_not_called()
