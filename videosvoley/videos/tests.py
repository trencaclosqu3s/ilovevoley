from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.utils import timezone

from videosvoley.videos.scraping import RFEVBPhaseParser, RFEVBTeamsParser


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

from videosvoley.videos.models import League, Team, Match, Standing, Category


class ScrapeRFEVBFaseCommandTests(TestCase):

    def setUp(self):
        self.category = Category.objects.create(name='Infantil Masculino')

        self.parent_league = League.objects.create(
            name='CEIM 2025-26',
            federation_id='ceim_2526',
            season='2025-26',
            competition_type='cup',
            match_format='standard',
            visibility_type='main',
            is_our_team_related=True,
        )
        self.parent_league.categories.add(self.category)

        self.sub_league = League.objects.create(
            name='CEIM 2025-26 - Grupo A',
            federation_id='ceim_2526_grupo_a',
            season='2025-26',
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
            'videosvoley.videos.scraping.RFEVBPhaseParser.fetch_content',
            return_value=PHASE_HTML,
        ), patch(
            'videosvoley.videos.scraping.RFEVBTeamsParser.fetch_content',
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
            season='2025-26',
            competition_type='cup',
            match_format='standard',
            visibility_type='main',
            is_our_team_related=True,
        )

    @patch('videosvoley.videos.tasks.scrape_rfevb_fases')
    @patch('videosvoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_calls_scrape_fases(self, mock_final, mock_scrape):
        from videosvoley.videos.tasks import scrape_rfevb_competition
        mock_scrape.return_value = {'matches_found': 10, 'created': 2, 'updated': 8,
                                    'skipped': 0, 'errors': []}
        scrape_rfevb_competition(9041, [2193, 2194], 'ceim_2526_task_test')
        mock_scrape.assert_called_once_with(9041, [2193, 2194], 'ceim_2526_task_test')

    @patch('videosvoley.videos.tasks.scrape_rfevb_fases')
    @patch('videosvoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_triggers_final_classification_when_all_done(self, mock_final, mock_scrape):
        from videosvoley.videos.tasks import scrape_rfevb_competition
        mock_scrape.return_value = {'matches_found': 0, 'created': 0, 'updated': 0,
                                    'skipped': 0, 'errors': []}
        # No hay partidos pendientes (BD vacía para esta liga)
        scrape_rfevb_competition(9041, [2193], 'ceim_2526_task_test')
        mock_final.delay.assert_called_once_with(9041, 'ceim_2526_task_test')

    @patch('videosvoley.videos.tasks.scrape_rfevb_fases')
    @patch('videosvoley.videos.tasks.scrape_rfevb_final_classification')
    def test_task_does_not_trigger_final_when_pending_matches(self, mock_final, mock_scrape):
        from videosvoley.videos.tasks import scrape_rfevb_competition
        from datetime import datetime
        from zoneinfo import ZoneInfo
        # Crear un partido pendiente
        sub = League.objects.create(
            name='Grupo A', federation_id='ceim_2526_task_test_grupo_a',
            season='2025-26', competition_type='cup', match_format='standard',
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
