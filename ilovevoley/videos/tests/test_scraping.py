from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.utils import timezone

from ilovevoley.videos.scraping import RFEVBPhaseParser, RFEVBTeamsParser, StandingsParser


# ---------------------------------------------------------------------------
# Fixtures HTML (ISO-8859-1 ya decodificado, como devuelve requests.text)
# ---------------------------------------------------------------------------

PHASE_HTML = """<!doctype html>
<html>
<head><meta charset='iso-8859-1'></head>
<body>
<div class="card">
  <h4> Grupo A</h4>
  <table class="table table-responsive">
    <tr>
      <th>1</th>
      <td>AD Eliocroca - CV Sant Josep</td>
      <td>27/05/26 (17:00)</td>
      <td>Pabellón Ciudad Deportiva</td>
      <td>3 - 1</td>
      <td>(25-20/25-18/20-25/25-22/0-0)</td>
    </tr>
    <tr>
      <th>2</th>
      <td>#= 1 Grupo B - #= 2 Grupo C</td>
      <td>28/05/26 (09:30)</td>
      <td>Pabellón Ciudad Deportiva</td>
      <td>0 - 0</td>
      <td>(0-0/0-0/0-0/0-0/0-0)</td>
    </tr>
    <tr>
      <th>3</th>
      <td>CV Oviedo - CD Las Viñas</td>
      <td>27/05/26 (19:00)</td>
      <td>Pabellón Ciudad Deportiva</td>
      <td>0 - 0</td>
      <td>(0-0/0-0/0-0/0-0/0-0)</td>
    </tr>
  </table>
  <table width="80%">
    <thead>
      <tr>
        <th colspan="2">CLASIFICACIÓN</th>
        <th>Ptos</th><th>J</th><th>G3</th><th>G2</th>
        <th>P1</th><th>P0</th><th>SF</th><th>SC</th><th>PF</th><th>PC</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>1</td>
        <td><img src="http://intranet.rfevb.com/clubes/logos/web/cl00922.png" width=30 height=30> AD Eliocroca</td>
        <td>3</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td>3</td><td>1</td><td>75</td><td>65</td>
      </tr>
      <tr>
        <td>2</td>
        <td><img src="http://intranet.rfevb.com/clubes/logos/web/cl00263.png" width=30 height=30> CV Sant Josep</td>
        <td>0</td><td>1</td><td>0</td><td>0</td><td>0</td><td>1</td><td>1</td><td>3</td><td>65</td><td>75</td>
      </tr>
    </tbody>
  </table>
</div>
<div class="card">
  <h4> 1 al 16</h4>
  <table class="table table-responsive">
    <tr>
      <th>49</th>
      <td>#= 1 Grupo A - #= 2 Grupo H</td>
      <td>29/05/26 (11:30)</td>
      <td>Pabellón Ciudad Deportiva</td>
      <td>0 - 0</td>
      <td>(0-0/0-0/0-0/0-0/0-0)</td>
    </tr>
  </table>
</div>
</body>
</html>"""

TEAMS_HTML = """<!doctype html>
<html>
<head><meta charset='iso-8859-1'></head>
<body>
<table class="table table-responsive">
  <tbody>
    <tr>
      <td>1</td>
      <td><img src="http://intranet.rfevb.com/clubes/logos/web/cl00922.png" width=30 height=30></td>
      <td>AD Eliocroca (MURCIA)</td>
      <td>A1</td>
    </tr>
    <tr>
      <td>2</td>
      <td><img src="http://intranet.rfevb.com/clubes/logos/web/cl00263.png" width=30 height=30></td>
      <td>CV Sant Josep (BALEARES)</td>
      <td>A2</td>
    </tr>
  </tbody>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# RFEVBPhaseParser tests
# ---------------------------------------------------------------------------

class RFEVBPhaseParserTests(TestCase):

    def _make_parser(self):
        mock_league = MagicMock()
        mock_league.match_format = 'standard'
        return RFEVBPhaseParser(mock_league)

    def test_parse_returns_two_groups(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        self.assertEqual(len(result['groups']), 2)

    def test_first_group_name(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        self.assertEqual(result['groups'][0]['name'], 'Grupo A')

    def test_second_group_name(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        self.assertEqual(result['groups'][1]['name'], '1 al 16')

    def test_placeholder_matches_filtered_out(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        grupo_a = result['groups'][0]
        match_numbers = [m['rfevb_match_number'] for m in grupo_a['matches']]
        self.assertNotIn(2, match_numbers)  # placeholder filtered
        self.assertIn(1, match_numbers)
        self.assertIn(3, match_numbers)

    def test_finished_match_parsed_correctly(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        match = result['groups'][0]['matches'][0]  # match 1: 3-1
        self.assertEqual(match['rfevb_match_number'], 1)
        self.assertEqual(match['home_team_name'], 'AD Eliocroca')
        self.assertEqual(match['away_team_name'], 'CV Sant Josep')
        self.assertEqual(match['home_score'], 3)
        self.assertEqual(match['away_score'], 1)
        self.assertEqual(match['status'], 'finished')
        self.assertEqual(match['venue'], 'Pabellón Ciudad Deportiva')

    def test_scheduled_match_has_none_scores(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        match = result['groups'][0]['matches'][1]  # match 3: 0-0
        self.assertIsNone(match['home_score'])
        self.assertIsNone(match['away_score'])
        self.assertEqual(match['status'], 'scheduled')

    def test_match_date_parsed(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        match = result['groups'][0]['matches'][0]
        self.assertEqual(match['match_date'].year, 2026)
        self.assertEqual(match['match_date'].month, 5)
        self.assertEqual(match['match_date'].day, 27)
        self.assertEqual(match['match_date'].hour, 17)
        self.assertEqual(match['match_date'].minute, 0)

    def test_group_without_standings_has_empty_list(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        grupo_1al16 = result['groups'][1]
        self.assertEqual(grupo_1al16['standings'], [])

    def test_all_placeholder_group_has_no_matches(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        grupo_1al16 = result['groups'][1]
        self.assertEqual(grupo_1al16['matches'], [])

    def test_standings_parsed_correctly(self):
        parser = self._make_parser()
        result = parser.parse_content(PHASE_HTML)
        standings = result['groups'][0]['standings']
        self.assertEqual(len(standings), 2)
        first = standings[0]
        self.assertEqual(first['position'], 1)
        self.assertEqual(first['team_name'], 'AD Eliocroca')
        self.assertEqual(first['total_points'], 3)
        self.assertEqual(first['played'], 1)
        self.assertEqual(first['won'], 1)    # G3=1, G2=0
        self.assertEqual(first['lost'], 0)   # P1=0, P0=0
        self.assertEqual(first['wins_3_0'], 1)  # stored as G3
        self.assertEqual(first['wins_3_2'], 0)  # G2
        self.assertEqual(first['losses_2_3'], 0)  # P1
        self.assertEqual(first['losses_0_3'], 0)  # P0
        self.assertEqual(first['sets_for'], 3)
        self.assertEqual(first['sets_against'], 1)
        self.assertEqual(first['points_for'], 75)
        self.assertEqual(first['points_against'], 65)


class StandingsParserTests(TestCase):
    """voleibolib no fija el orden de columnas: la liga 7990 publica `PG PP NP`."""

    HTML = """<table class="clasificacion">
<tr><th></th><th>Equipo</th><th>PJ</th><th>PG</th><th>PP</th><th>NP</th><th>JF</th><th>JC</th>
<th>TF</th><th>TC</th><th>PT</th><th>G3</th><th>G2</th><th>P1</th><th>P0</th></tr>
<tr><td>3.</td><td>CAIXA COLONYA CV MANACOR</td><td>11</td><td>6</td><td>4</td><td>1</td><td>19</td>
<td>15</td><td>703</td><td>632</td><td>17</td><td>5</td><td>1</td><td>0</td><td>4</td></tr>
</table>"""

    def test_maps_columns_by_header_name(self):
        row = StandingsParser(MagicMock()).parse_content(self.HTML)['standings'][0]
        self.assertEqual(row['position'], 3)
        self.assertEqual(row['played'], 11)
        self.assertEqual(row['won'], 6)
        self.assertEqual(row['lost'], 4)  # no la columna NP
        self.assertEqual(row['total_points'], 17)
        # G3 agrupa 3-0 y 3-1; P0 agrupa 0-3 y 1-3
        self.assertEqual(row['wins_3_0'], 5)
        self.assertEqual(row['wins_3_2'], 1)
        self.assertEqual(row['losses_2_3'], 0)
        self.assertEqual(row['losses_0_3'], 4)
        self.assertNotIn('wins_3_1', row)


# ---------------------------------------------------------------------------
# RFEVBTeamsParser tests
# ---------------------------------------------------------------------------

class RFEVBTeamsParserTests(TestCase):

    def _make_parser(self):
        return RFEVBTeamsParser(MagicMock())

    def test_returns_two_teams(self):
        parser = self._make_parser()
        result = parser.parse_content(TEAMS_HTML)
        self.assertEqual(len(result['teams']), 2)

    def test_region_stripped_from_name(self):
        parser = self._make_parser()
        result = parser.parse_content(TEAMS_HTML)
        self.assertIn('AD Eliocroca', result['teams'])
        self.assertIn('CV Sant Josep', result['teams'])
        self.assertNotIn('AD Eliocroca (MURCIA)', result['teams'])

    def test_logo_url_extracted(self):
        parser = self._make_parser()
        result = parser.parse_content(TEAMS_HTML)
        self.assertEqual(
            result['teams']['AD Eliocroca'],
            'http://intranet.rfevb.com/clubes/logos/web/cl00922.png',
        )


# ---------------------------------------------------------------------------
# scrape_rfevb_fase command tests
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
from django.core.management import call_command
from io import StringIO

from ilovevoley.core.models import Season
from ilovevoley.videos.models import League, Team, Match, Standing, Category


class ScrapeRFEVBFaseCommandTests(TestCase):

    def setUp(self):
        self.category = Category.objects.create(name='Infantil Masculino')

        self.parent_league = League.objects.create(
            name='CEIM 2025-26',
            federation_id='ceim_2526',
            season=Season.objects.resolve('2025-26'),
            competition_type='cup',
            match_format='standard',
            visibility_type='main',
            is_our_team_related=True,
        )
        self.parent_league.categories.add(self.category)

        self.sub_league = League.objects.create(
            name='CEIM 2025-26 - Grupo A',
            federation_id='ceim_2526_grupo_a',
            season=Season.objects.resolve('2025-26'),
            competition_type='cup',
            match_format='standard',
            visibility_type='main',
            is_our_team_related=True,
            parent_league=self.parent_league,
            phase_name='Grupo A',
        )

        self.team_home = Team.objects.create(
            name='AD Eliocroca',
            federation_id='ceim_2526_a1',
            is_active=True,
        )
        self.team_away = Team.objects.create(
            name='CV Sant Josep',
            federation_id='ceim_2526_a2',
            is_active=True,
        )
        self.team_oviedo = Team.objects.create(
            name='CV Oviedo',
            federation_id='ceim_2526_c2',
            is_active=True,
        )
        self.team_viñas = Team.objects.create(
            name='CD Las Viñas',
            federation_id='ceim_2526_c4',
            is_active=True,
        )

        # Match preexistente sin federation_id (creado por create_ceim_2526)
        from django.utils import timezone as tz
        from datetime import datetime
        from zoneinfo import ZoneInfo
        MADRID = ZoneInfo('Europe/Madrid')
        self.existing_match = Match.objects.create(
            league=self.sub_league,
            home_team=self.team_home,
            away_team=self.team_away,
            match_date=datetime(2026, 5, 27, 17, 0, tzinfo=MADRID),
            status='scheduled',
        )

    def _run_command(self, fase_ids='2193', dry_run=False):
        """Ejecuta el comando mockeando las llamadas HTTP."""
        out = StringIO()
        with patch(
            'ilovevoley.videos.scraping.RFEVBPhaseParser.fetch_content',
            return_value=PHASE_HTML,
        ), patch(
            'ilovevoley.videos.scraping.RFEVBTeamsParser.fetch_content',
            return_value=TEAMS_HTML,
        ):
            call_command(
                'scrape_rfevb_fase',
                competition_id=9041,
                fase_ids=fase_ids,
                parent_league='ceim_2526',
                dry_run=dry_run,
                delay=0,
                stdout=out,
            )
        return out.getvalue()

    def test_existing_match_updated_with_result(self):
        self._run_command()
        self.existing_match.refresh_from_db()
        self.assertEqual(self.existing_match.home_score, 3)
        self.assertEqual(self.existing_match.away_score, 1)
        self.assertEqual(self.existing_match.status, 'finished')

    def test_existing_match_anchored_with_federation_id(self):
        self._run_command()
        self.existing_match.refresh_from_db()
        self.assertEqual(self.existing_match.federation_id, 'rfevb_9041_1')

    def test_scheduled_match_created_for_oviedo_viñas(self):
        self._run_command()
        match = Match.objects.filter(
            league=self.sub_league,
            home_team=self.team_oviedo,
            away_team=self.team_viñas,
        ).first()
        self.assertIsNotNone(match)
        self.assertEqual(match.status, 'scheduled')
        self.assertEqual(match.federation_id, 'rfevb_9041_3')

    def test_placeholder_matches_not_created(self):
        self._run_command()
        # Match number 2 is a placeholder → should not exist
        self.assertFalse(
            Match.objects.filter(federation_id='rfevb_9041_2').exists()
        )

    def test_subleague_found_by_phase_name(self):
        """El comando encuentra la sub-liga existente por phase_name, no crea una nueva."""
        self._run_command()
        count = League.objects.filter(parent_league=self.parent_league).count()
        self.assertEqual(count, 1)  # solo la sub-liga 'Grupo A' ya existente

    def test_standings_updated(self):
        self._run_command()
        standing = Standing.objects.filter(
            league=self.sub_league, team=self.team_home
        ).first()
        self.assertIsNotNone(standing)
        self.assertEqual(standing.total_points, 3)
        self.assertEqual(standing.position, 1)
        self.assertEqual(standing.played, 1)
        self.assertEqual(standing.won, 1)
        self.assertEqual(standing.sets_for, 3)
        self.assertEqual(standing.sets_against, 1)

    def test_team_logo_updated(self):
        self.assertFalse(self.team_home.logo_url)
        self._run_command()
        self.team_home.refresh_from_db()
        self.assertEqual(
            self.team_home.logo_url,
            'http://intranet.rfevb.com/clubes/logos/web/cl00922.png',
        )

    def test_dry_run_makes_no_changes(self):
        self._run_command(dry_run=True)
        self.existing_match.refresh_from_db()
        self.assertIsNone(self.existing_match.home_score)
        self.assertEqual(self.existing_match.status, 'scheduled')

    def test_second_call_is_idempotent(self):
        self._run_command()
        self._run_command()
        count = Match.objects.filter(
            league=self.sub_league,
            federation_id__startswith='rfevb_9041_',
        ).count()
        # Solo los 2 partidos reales del Grupo A (match 1 y match 3)
        self.assertEqual(count, 2)


# ---------------------------------------------------------------------------
# Celery tasks tests
# ---------------------------------------------------------------------------

class ScrapeRFEVBCompetitionTaskTests(TestCase):

    def setUp(self):
        self.category = Category.objects.get_or_create(name='Infantil Masculino')[0]
        self.parent_league = League.objects.create(
            name='CEIM 2025-26',
            federation_id='ceim_2526_task_test',
            season=Season.objects.resolve('2025-26'),
            competition_type='cup',
            match_format='standard',
            visibility_type='main',
            is_our_team_related=True,
        )

    @patch('ilovevoley.videos.tasks.scrape_rfevb_fases')
    @patch('ilovevoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_calls_scrape_fases(self, mock_final, mock_scrape):
        from ilovevoley.videos.tasks import scrape_rfevb_competition
        mock_scrape.return_value = {'matches_found': 10, 'created': 2, 'updated': 8,
                                    'skipped': 0, 'errors': []}
        scrape_rfevb_competition(9041, [2193, 2194], 'ceim_2526_task_test')
        mock_scrape.assert_called_once_with(9041, [2193, 2194], 'ceim_2526_task_test')

    @patch('ilovevoley.videos.tasks.scrape_rfevb_fases')
    @patch('ilovevoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_triggers_final_classification_when_all_done(self, mock_final, mock_scrape):
        from ilovevoley.videos.tasks import scrape_rfevb_competition
        mock_scrape.return_value = {'matches_found': 0, 'created': 0, 'updated': 0,
                                    'skipped': 0, 'errors': []}
        # No hay partidos pendientes (BD vacía para esta liga)
        scrape_rfevb_competition(9041, [2193], 'ceim_2526_task_test')
        mock_final.delay.assert_called_once_with(9041, 'ceim_2526_task_test')

    @patch('ilovevoley.videos.tasks.scrape_rfevb_fases')
    @patch('ilovevoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_does_not_trigger_final_when_pending_matches(self, mock_final, mock_scrape):
        from ilovevoley.videos.tasks import scrape_rfevb_competition
        from datetime import datetime
        from zoneinfo import ZoneInfo
        # Crear un partido pendiente
        sub = League.objects.create(
            name='Grupo A', federation_id='ceim_2526_task_test_grupo_a',
            season=Season.objects.resolve('2025-26'), competition_type='cup', match_format='standard',
            visibility_type='main', is_our_team_related=True,
            parent_league=self.parent_league, phase_name='Grupo A',
        )
        t1 = Team.objects.create(name='TeamX', federation_id='task_test_tx', is_active=True)
        t2 = Team.objects.create(name='TeamY', federation_id='task_test_ty', is_active=True)
        Match.objects.create(
            league=sub, home_team=t1, away_team=t2,
            match_date=datetime(2026, 5, 27, 17, 0, tzinfo=ZoneInfo('Europe/Madrid')),
            status='scheduled',
        )
        mock_scrape.return_value = {'matches_found': 1, 'created': 0, 'updated': 0,
                                    'skipped': 0, 'errors': []}
        scrape_rfevb_competition(9041, [2193], 'ceim_2526_task_test')
        mock_final.delay.assert_not_called()

    @patch('ilovevoley.videos.tasks.scrape_rfevb_fases')
    @patch('ilovevoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_returns_error_without_triggering_final_when_league_not_found(self, mock_final, mock_scrape):
        from ilovevoley.videos.tasks import scrape_rfevb_competition
        mock_scrape.return_value = {'error': 'Liga padre no encontrada: nonexistent'}
        result = scrape_rfevb_competition(9041, [2193], 'nonexistent')
        self.assertIn('error', result)
        mock_final.delay.assert_not_called()


# ---------------------------------------------------------------------------
# JSON unified match processing tests
# ---------------------------------------------------------------------------

class ProcessJsonMatchesUnifiedTests(TestCase):

    def setUp(self):
        from ilovevoley.videos.scraping import FederationScraper
        self.category = Category.objects.create(name='Juvenil')
        self.league = League.objects.create(
            name='Juvenil Masculino',
            federation_id='8246',
            season=Season.objects.resolve('2026-27'),
            competition_type='regular',
            match_format='standard',
            visibility_type='main',
        )
        self.league.categories.add(self.category)
        self.home_team = Team.objects.create(
            name='CLUB VOLEIBOL EIVISSA',
            federation_id='8246_club_voleibol_eivissa',
            category=self.category,
            is_active=True,
        )
        self.away_team = Team.objects.create(
            name='CD MESTRAL IBIZA VOLEY',
            federation_id='8246_cd_mestral_ibiza_voley',
            category=self.category,
            is_active=True,
        )
        self.scraper = FederationScraper(self.league)

    def test_updates_existing_match_when_date_or_time_changed(self):
        from zoneinfo import ZoneInfo
        from datetime import datetime

        # Match was previously saved with 10:00
        old_date = datetime(2026, 10, 3, 10, 0, tzinfo=ZoneInfo('Europe/Madrid'))
        existing_match = Match.objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=old_date,
            federation_id='85843',
            status='scheduled',
        )

        # JSON brings the match with ID 85843, but time changed to 12:00
        partidos_data = [{
            'ID': 85843,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'Campo': 'Es Viver',
            'Municipio': 'Eivissa',
            'TORNEO': 8246,
        }]

        created, updated = self.scraper._process_json_matches_unified(
            self.league, partidos_data, 'Juvenil', '8246', '1'
        )

        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        existing_match.refresh_from_db()
        expected_date = datetime(2026, 10, 3, 12, 0, tzinfo=ZoneInfo('Europe/Madrid'))
        self.assertEqual(existing_match.match_date, expected_date)
        self.assertEqual(existing_match.venue, 'Es Viver')

    def test_updates_existing_withdrawn_match_by_federation_id(self):
        from zoneinfo import ZoneInfo
        from datetime import datetime

        match_date = datetime(2026, 10, 3, 12, 0, tzinfo=ZoneInfo('Europe/Madrid'))
        existing_match = Match.all_objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=match_date,
            federation_id='85843',
            status='withdrawn',
        )

        partidos_data = [{
            'ID': 85843,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'TORNEO': 8246,
        }]

        created, updated = self.scraper._process_json_matches_unified(
            self.league, partidos_data, 'Juvenil', '8246', '1'
        )

        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        existing_match.refresh_from_db()
        self.assertEqual(existing_match.status, 'scheduled')

    def test_does_not_reactivate_withdrawn_match_while_team_inactive(self):
        """El JSON no debe resucitar un partido retirado si el equipo sigue inactivo (#235)."""
        from zoneinfo import ZoneInfo
        from datetime import datetime

        self.home_team.is_active = False
        self.home_team.save(update_fields=['is_active'])

        match_date = datetime(2026, 10, 3, 12, 0, tzinfo=ZoneInfo('Europe/Madrid'))
        existing_match = Match.all_objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=match_date,
            federation_id='85843',
            status='withdrawn',
        )

        partidos_data = [{
            'ID': 85843,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'TORNEO': 8246,
        }]

        self.scraper._process_json_matches_unified(
            self.league, partidos_data, 'Juvenil', '8246', '1'
        )

        existing_match.refresh_from_db()
        self.assertEqual(existing_match.status, 'withdrawn')
        from ilovevoley.competitions.models import MatchChangeLog
        self.assertEqual(
            MatchChangeLog.objects.filter(match=existing_match, change_type='status').count(), 0
        )

    def test_links_federation_id_to_existing_match_without_id_on_same_day(self):
        from zoneinfo import ZoneInfo
        from datetime import datetime

        # Match was previously created from HTML calendar without federation_id, e.g. at 00:00
        old_date = datetime(2026, 10, 3, 0, 0, tzinfo=ZoneInfo('Europe/Madrid'))
        existing_match = Match.objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=old_date,
            federation_id=None,
            status='scheduled',
            round_number=3,
        )

        partidos_data = [{
            'ID': 85843,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'TORNEO': 8246,
        }]

        created, updated = self.scraper._process_json_matches_unified(
            self.league, partidos_data, 'Juvenil', '8246', '1'
        )

        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)
        existing_match.refresh_from_db()
        self.assertEqual(existing_match.federation_id, '85843')
        # Preserves original round_number if JSON defaulted to 1
        self.assertEqual(existing_match.round_number, 3)
        # Total matches in DB should remain 1, no duplicate created
        self.assertEqual(Match.all_objects.count(), 1)

    def test_creates_match_with_canonical_acta_url_from_relative_json_value(self):
        """El JSON federativo sirve sólo 'acta_XXXX.html'; debe guardarse la URL canónica completa."""
        partidos_data = [{
            'ID': 85846,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'TORNEO': 8246,
            'acta_html': 'acta_10932.html',
        }]

        created, updated = self.scraper._process_json_matches_unified(
            self.league, partidos_data, 'Juvenil', '8246', '1'
        )

        self.assertEqual(created, 1)
        match = Match.objects.get(federation_id='85846')
        self.assertEqual(
            match.acta_html,
            'https://voleibolib.federatio.com/actas/85846/acta_10932.html',
        )

    def test_updates_match_with_canonical_acta_url_and_preserves_existing(self):
        """Normaliza el acta al actualizar y no borra el acta oficial si un JSON posterior viene sin ella."""
        from zoneinfo import ZoneInfo
        from datetime import datetime

        match_date = datetime(2026, 10, 3, 12, 0, tzinfo=ZoneInfo('Europe/Madrid'))
        match = Match.objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=match_date,
            federation_id='85846',
            status='scheduled',
        )

        partidos_data = [{
            'ID': 85846,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'TORNEO': 8246,
            'acta_html': 'acta_10932.html',
        }]

        self.scraper._process_json_matches_unified(
            self.league, partidos_data, 'Juvenil', '8246', '1'
        )
        match.refresh_from_db()
        self.assertEqual(
            match.acta_html,
            'https://voleibolib.federatio.com/actas/85846/acta_10932.html',
        )

        # Segundo scrape donde el JSON no envía acta (p. ej. campo vacío o ausente):
        partidos_data_sin_acta = [{
            'ID': 85846,
            'ELOCAL': 'CLUB VOLEIBOL EIVISSA',
            'EVISITANTE': 'CD MESTRAL IBIZA VOLEY',
            'FECHA': '03/10/2026',
            'HORA': '12:00',
            'TORNEO': 8246,
            'acta_html': '',
        }]
        self.scraper._process_json_matches_unified(
            self.league, partidos_data_sin_acta, 'Juvenil', '8246', '1'
        )
        match.refresh_from_db()
        self.assertEqual(
            match.acta_html,
            'https://voleibolib.federatio.com/actas/85846/acta_10932.html',
        )


# ---------------------------------------------------------------------------
# Withdrawn team detection: evaluación una sola vez con la unión del scrape (#235)
# ---------------------------------------------------------------------------

class WithdrawnTeamDetectionTests(TestCase):

    def setUp(self):
        from datetime import timedelta
        from ilovevoley.videos.scraping import FederationScraper

        self.category = Category.objects.create(name='Juvenil')
        self.league = League.objects.create(
            name='Juvenil Masculino',
            federation_id='8246',
            season=Season.objects.resolve('2026-27'),
            competition_type='regular',
            match_format='standard',
            visibility_type='main',
        )
        self.league.categories.add(self.category)
        self.team_a = Team.objects.create(
            name='EQUIPO A', federation_id='g_a', category=self.category, is_active=True
        )
        self.team_b = Team.objects.create(
            name='EQUIPO B', federation_id='g_b', category=self.category, is_active=True
        )
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now() + timedelta(days=3),
            status='scheduled',
        )
        self.scraper = FederationScraper(self.league)

    def test_partial_update_teams_does_not_deactivate_absent_teams(self):
        """Un scrape parcial (una sola jornada/endpoint) no debe retirar al resto de equipos."""
        self.scraper.update_teams([{'name': 'EQUIPO A', 'federation_id': 'g_a'}])

        self.team_b.refresh_from_db()
        self.assertTrue(self.team_b.is_active)

    def test_detect_withdrawn_teams_deactivates_absent_and_withdraws_match(self):
        self.scraper.detect_withdrawn_teams({'g_a'})

        self.team_b.refresh_from_db()
        self.match.refresh_from_db()
        self.assertFalse(self.team_b.is_active)
        self.assertEqual(self.match.status, 'withdrawn')

    def test_detect_withdrawn_teams_keeps_teams_present_in_union(self):
        self.scraper.detect_withdrawn_teams({'g_a', 'g_b'})

        self.team_a.refresh_from_db()
        self.team_b.refresh_from_db()
        self.match.refresh_from_db()
        self.assertTrue(self.team_a.is_active)
        self.assertTrue(self.team_b.is_active)
        self.assertEqual(self.match.status, 'scheduled')


# ---------------------------------------------------------------------------
# Identidad de equipos: el id de club federativo manda sobre el nombre (#380)
# ---------------------------------------------------------------------------

class UpdateTeamsFederationClubTests(TestCase):

    def setUp(self):
        from ilovevoley.teams.models import Club
        from ilovevoley.videos.scraping import FederationScraper

        self.category = Category.objects.create(name='Senior')
        self.league = League.objects.create(
            name='Superliga 2', federation_id='9001', season=Season.objects.resolve('2026-27'),
            competition_type='regular', match_format='standard', visibility_type='main',
        )
        self.league.categories.add(self.category)
        self.mataro = Club.objects.create(federation_id='10', official_name='CV MATARO')
        self.mayurqa = Club.objects.create(federation_id='20', official_name='CLUB MAYURQA')
        self.scraper = FederationScraper(self.league)

    def test_sponsor_rename_keeps_team_in_its_club(self):
        """El equipo renombrado por patrocinador es otra fila, pero el id de club lo sitúa."""
        teams = self.scraper.update_teams([
            {'name': 'PEP MASCARO CMV PORTOL ROJO', 'federation_id': 'g_new', 'federation_club_id': '10'},
        ])

        self.assertEqual(teams['PEP MASCARO CMV PORTOL ROJO'].club, self.mataro)

    def test_name_match_from_other_club_is_not_reused(self):
        """Un nombre coincidente de otro club no se adueña del federation_id."""
        other = Team.objects.create(
            name='CV ATLETICO', federation_id='g_old', category=self.category, club=self.mayurqa,
        )

        teams = self.scraper.update_teams([
            {'name': 'CV ATLETICO', 'federation_id': 'g_new', 'federation_club_id': '10'},
        ])

        other.refresh_from_db()
        self.assertEqual(other.federation_id, 'g_old')
        self.assertNotEqual(teams['CV ATLETICO'].pk, other.pk)
        self.assertEqual(teams['CV ATLETICO'].club, self.mataro)


# ---------------------------------------------------------------------------
# Parciales: validación manual, parseo del .asp y penalización
# ---------------------------------------------------------------------------

from ilovevoley.videos.scraping import (  # noqa: E402
    MatchesParser,
    is_penalty_result,
    parse_set_scores_string,
    validate_set_scores,
)


class ValidateSetScoresTests(TestCase):
    """Regla de puntos de los parciales de entrada manual."""

    def setUp(self):
        self.standard = League(match_format='standard')
        self.three = League(match_format='tournament_3sets')
        self.alevin = League(match_format='alevin_balear')

    def test_empty_is_valid(self):
        self.assertTrue(validate_set_scores([], self.standard))
        self.assertTrue(validate_set_scores(None, self.standard))

    def test_standard_best_of_five_with_tiebreak(self):
        scores = [[25, 20], [20, 25], [25, 22], [20, 25], [15, 12]]
        self.assertTrue(validate_set_scores(scores, self.standard))

    def test_standard_sweep_all_sets_to_25(self):
        self.assertTrue(validate_set_scores([[25, 20], [25, 18], [25, 22]], self.standard))

    def test_set_without_two_point_lead_is_invalid(self):
        self.assertFalse(validate_set_scores([[25, 24], [25, 20], [25, 20]], self.standard))

    def test_deuce_set_is_valid(self):
        self.assertTrue(validate_set_scores([[26, 24], [20, 25], [25, 18], [25, 17]], self.standard))

    def test_deciding_set_below_15_is_invalid(self):
        scores = [[25, 20], [20, 25], [25, 22], [20, 25], [14, 12]]
        self.assertFalse(validate_set_scores(scores, self.standard))

    def test_deciding_set_without_two_point_lead_is_invalid(self):
        scores = [[25, 20], [20, 25], [25, 22], [20, 25], [15, 14]]
        self.assertFalse(validate_set_scores(scores, self.standard))

    def test_three_set_format_short_match_uses_25(self):
        # 2-0: no llega al máximo, ningún set es decisivo
        self.assertTrue(validate_set_scores([[25, 20], [25, 18]], self.three))

    def test_three_set_format_decider_to_15(self):
        self.assertTrue(validate_set_scores([[25, 20], [20, 25], [15, 11]], self.three))

    def test_alevin_last_set_to_15(self):
        self.assertTrue(validate_set_scores([[25, 20], [25, 18], [15, 12]], self.alevin))

    def test_derived_score_must_be_valid(self):
        # 2 sets repartidos -> 1-1 no es un marcador válido
        self.assertFalse(validate_set_scores([[25, 20], [20, 25]], self.standard))


class ParseSetScoresStringTests(TestCase):
    def test_parses_slash_separated(self):
        self.assertEqual(
            parse_set_scores_string('25-10/25-15/25-11'),
            [[25, 10], [25, 15], [25, 11]],
        )

    def test_returns_none_for_empty(self):
        self.assertIsNone(parse_set_scores_string(''))
        self.assertIsNone(parse_set_scores_string(None))

    def test_returns_none_for_garbage(self):
        self.assertIsNone(parse_set_scores_string('sin datos'))


class PenaltyDetectionTests(TestCase):
    def test_all_sets_to_zero_marked(self):
        self.assertTrue(is_penalty_result([[25, 0], [25, 0], [25, 0]]))

    def test_away_penalty_marked(self):
        self.assertTrue(is_penalty_result([[0, 25], [0, 25], [0, 25]]))

    def test_normal_result_not_marked(self):
        self.assertFalse(is_penalty_result([[25, 20], [20, 25], [25, 22]]))

    def test_mixed_zero_not_marked(self):
        self.assertFalse(is_penalty_result([[25, 0], [25, 20]]))


class MatchesParserSetScoresTests(TestCase):
    """El .asp de resultados publica los parciales en el segundo marcador."""

    def setUp(self):
        self.league = League.objects.create(
            name='Senior', federation_id='p-1', match_format='standard',
            season=Season.objects.resolve('2026-27'), competition_type='regular',
        )
        self.parser = MatchesParser(self.league)

    def _content(self, sets_html):
        return (
            "<h3>JORNADA 1</h3>"
            "<div class='info_partido little' align='center'>"
            "  <div class='top'><span class='municipio'>Palma</span>"
            "    <span class='fecha'>26/09/2026 - 17:00</span></div>"
            "  <div class='datos_partido'>"
            "    <span class='nombreEquipo'>LOCAL</span>"
            "    <span class='marcador'>3 - 0</span>"
            "    <span class='nombreEquipo'>VISITANTE</span>"
            "  </div>"
            "  <div class='estado_partido' id='finalizado'>"
            f"    <span class='marcador'>{sets_html}</span>"
            "  </div>"
            "</div>"
        )

    def test_extracts_set_scores(self):
        data = self.parser.parse_content(self._content('25-10/25-15/25-11'))
        self.assertEqual(data['matches'][0]['set_scores'], [[25, 10], [25, 15], [25, 11]])

    def test_no_sets_span_means_none(self):
        data = self.parser.parse_content(self._content(''))
        self.assertIsNone(data['matches'][0]['set_scores'])


class UpdateMatchesSetScoresTests(TestCase):
    """Los parciales del scraping se persisten sin pisar correcciones previas."""

    def setUp(self):
        from ilovevoley.videos.scraping import FederationScraper
        self.category = Category.objects.create(name='Senior')
        self.league = League.objects.create(
            name='Senior', federation_id='8247', match_format='standard',
            season=Season.objects.resolve('2026-27'), competition_type='regular',
        )
        self.league.categories.add(self.category)
        self.home = Team.objects.create(
            name='LOCAL', federation_id='u_local', category=self.category, is_active=True,
        )
        self.away = Team.objects.create(
            name='VISITANTE', federation_id='u_away', category=self.category, is_active=True,
        )
        self.scraper = FederationScraper(self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), round_number=1, status='finished',
            home_score=3, away_score=0,
        )

    def _match_data(self, set_scores):
        return {
            'home_team': 'LOCAL', 'away_team': 'VISITANTE',
            'home_score': 3, 'away_score': 0, 'status': 'finished',
            'round_number': 1, 'set_scores': set_scores,
        }

    def test_persists_set_scores_and_marks_penalty(self):
        self.scraper.update_matches([self._match_data([[25, 0], [25, 0], [25, 0]])], {})
        self.match.refresh_from_db()
        self.assertEqual(self.match.set_scores, [[25, 0], [25, 0], [25, 0]])
        self.assertTrue(self.match.result_penalized)

    def test_does_not_overwrite_existing_set_scores(self):
        self.match.set_scores = [[25, 20], [25, 18], [25, 22]]
        self.match.save(update_fields=['set_scores'])

        self.scraper.update_matches([self._match_data([[25, 0], [25, 0], [25, 0]])], {})

        self.match.refresh_from_db()
        self.assertEqual(self.match.set_scores, [[25, 20], [25, 18], [25, 22]])
        self.assertFalse(self.match.result_penalized)


class UpdateMatchesResultPersistenceTests(TestCase):
    """El resultado scrapeado de un partido existente llega a base de datos (#286).

    La ruta de merge busca por jornada un partido programado sin marcador y
    vuelca el resultado final. El detector de cambios no debe adelantar el
    marcador en memoria: si lo hace, el merge no ve campos por actualizar y el
    resultado se pierde aunque el push de aviso salga.
    """

    def setUp(self):
        from ilovevoley.videos.scraping import FederationScraper
        self.category = Category.objects.create(name='Senior')
        self.league = League.objects.create(
            name='Senior', federation_id='8247', match_format='standard',
            season=Season.objects.resolve('2026-27'), competition_type='regular',
        )
        self.league.categories.add(self.category)
        self.home = Team.objects.create(
            name='LOCAL', federation_id='u_local', category=self.category, is_active=True,
        )
        self.away = Team.objects.create(
            name='VISITANTE', federation_id='u_away', category=self.category, is_active=True,
        )
        self.scraper = FederationScraper(self.league)
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), round_number=1, status='scheduled',
        )

    def _match_data(self):
        return {
            'home_team': 'LOCAL', 'away_team': 'VISITANTE',
            'home_score': 3, 'away_score': 1, 'status': 'finished',
            'round_number': 1, 'set_scores': [[25, 20], [20, 25], [25, 18], [25, 22]],
        }

    @patch('ilovevoley.videos.scraping.federation.notify_match_result_after_save')
    def test_scraped_result_is_persisted(self, mock_notify_after_save):
        self.scraper.update_matches([self._match_data()], {})

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, 'finished')
        self.assertEqual(self.match.home_score, 3)
        self.assertEqual(self.match.away_score, 1)
        self.assertEqual(self.match.set_scores, [[25, 20], [20, 25], [25, 18], [25, 22]])
        mock_notify_after_save.assert_called_once()
        self.assertFalse(mock_notify_after_save.call_args[0][1])


# ---------------------------------------------------------------------------
# Jornada real en partidos del JSON unificado (#369)
# ---------------------------------------------------------------------------

def _results_html(round_number, home_club, away_club):
    return (
        f"<h3>JORNADA {round_number}</h3><div class='info_partido little'>"
        f"<img src='https://x//fichas/clubes/{home_club}mini.jpg?1'>"
        f"<img src='https://x//fichas/clubes/{away_club}mini.jpg?1'></div>"
    )


class RoundFixtureMixin:
    """Liga 8248 con dos equipos, compartida por los tests de jornada."""

    def setUp(self):
        category = Category.objects.create(name='Senior')
        self.league = League.objects.create(
            name='Liga 8248', federation_id='8248', season=Season.objects.resolve('2025-26'),
            competition_type='league', match_format='standard', visibility_type='main',
        )
        self.league.categories.add(category)
        Team.objects.create(name='Club A', federation_id='a', category=category, is_active=True)
        Team.objects.create(name='Club B', federation_id='b', category=category, is_active=True)


class JSONRoundNumberTests(RoundFixtureMixin, TestCase):
    """El JSON no trae jornada: se cruza con el HTML de resultados por club local/visitante."""

    def _partido(self, fed_id, local, visitante, club_local, club_visitante, fecha):
        return {
            'ID': fed_id, 'ELOCAL': local, 'EVISITANTE': visitante, 'FECHA': fecha, 'HORA': '12:00',
            'ID_CLUB_LOCAL': club_local, 'ID_CLUB_VISITANTE': club_visitante,
            'RESULTADO_LOCAL': None, 'RESULTADO_VISITANTE': None,
        }

    @patch('ilovevoley.videos.scraping.federation.FederationScraper._fetch_json_with_retry')
    def test_ida_y_vuelta_get_their_own_round_and_existing_match_is_corrected(self, fetch):
        from ilovevoley.videos.scraping.federation import FederationScraper

        # Sin jor = jornada actual (1); con jor, esa jornada. Fuera de rango el servidor devuelve la 1.
        pages = {'jor=2': _results_html(2, 20, 10)}
        fetch.side_effect = lambda url: MagicMock(
            text=next((v for k, v in pages.items() if k in url), _results_html(1, 10, 20))
        )

        # Partido ya importado antes con la jornada falsa por defecto.
        a, b = Team.objects.get(name='Club A'), Team.objects.get(name='Club B')
        Match.objects.create(
            league=self.league, home_team=a, away_team=b, federation_id='1',
            match_date=timezone.make_aware(timezone.datetime(2026, 10, 11, 12, 0)), round_number=1,
        )
        scraper = FederationScraper(self.league)
        scraper._process_json_matches_unified(
            self.league,
            [
                self._partido('1', 'Club A', 'Club B', 10, 20, '11/10/2026'),
                self._partido('2', 'Club B', 'Club A', 20, 10, '18/10/2026'),
            ],
            'Senior', '8248', '1', round_map=scraper._fetch_round_map(self.league, {('10', '20'), ('20', '10')}),
        )

        self.assertEqual(fetch.call_count, 2)  # jornada actual + la contigua; no recorre la liga entera
        self.assertEqual(Match.objects.get(federation_id='1').round_number, 1)
        self.assertEqual(Match.objects.get(federation_id='2').round_number, 2)

    @patch('ilovevoley.videos.scraping.federation.FederationScraper._fetch_json_with_retry',
           side_effect=Exception('boom'))
    def test_round_map_failure_does_not_block_import(self, fetch):
        from ilovevoley.videos.scraping.federation import FederationScraper

        self.assertEqual(FederationScraper(self.league)._fetch_round_map(self.league, {('10', '20')}), {})


class BackfillMatchRoundsCommandTests(RoundFixtureMixin, TestCase):
    """El histórico con jornada falsa 1 se corrige recorriendo la liga entera, y dry-run no guarda."""

    @patch('ilovevoley.videos.scraping.federation.FederationScraper._fetch_json_with_retry')
    def test_backfill_fixes_vuelta_and_dry_run_changes_nothing(self, fetch):
        from ilovevoley.teams.models import Club

        pages = {'jor=1': _results_html(1, 10, 20), 'jor=2': _results_html(2, 20, 10)}
        # jor=3 fuera de rango: el servidor devuelve la jornada 1, que debe cortar el recorrido.
        fetch.side_effect = lambda url: MagicMock(
            text=next((v for k, v in pages.items() if k in url), _results_html(1, 10, 20))
        )
        club_a = Club.objects.create(federation_id='10')
        club_b = Club.objects.create(federation_id='20')
        a = Team.objects.get(name='Club A')
        b = Team.objects.get(name='Club B')
        a.club, b.club = club_a, club_b
        a.save()
        b.save()
        date = timezone.now()
        Match.objects.create(league=self.league, home_team=a, away_team=b, match_date=date, round_number=1)
        vuelta = Match.objects.create(league=self.league, home_team=b, away_team=a, match_date=date, round_number=1)

        call_command('backfill_match_rounds', '--dry-run', '--delay', '0', stdout=StringIO())
        vuelta.refresh_from_db()
        self.assertEqual(vuelta.round_number, 1)

        call_command('backfill_match_rounds', '--delay', '0', stdout=StringIO())
        vuelta.refresh_from_db()
        self.assertEqual(vuelta.round_number, 2)
