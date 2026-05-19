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
