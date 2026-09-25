from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.utils import timezone

from ilovevoley.videos.scraping import RFEVBPhaseParser, RFEVBTeamsParser


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




