# RFEVB Phase Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir scraping HTML para campeonatos nacionales RFEVB: parser reutilizable, comando de gestión genérico y tarea Celery con trigger de clasificación final.

**Architecture:** `RFEVBPhaseParser` y `RFEVBTeamsParser` se añaden a `scraping.py` heredando de `BaseParser`. El comando `scrape_rfevb_fase` orquesta fetch + actualizaciones de BD. La función core `scrape_rfevb_fases()` se importa tanto desde el comando como desde las tareas Celery para evitar duplicación.

**Tech Stack:** BeautifulSoup4, requests, unidecode, Django management commands, Celery `@shared_task`

---

## Mapa de ficheros

| Fichero | Acción | Responsabilidad |
|---------|--------|-----------------|
| `videosvoley/videos/scraping.py` | Modificar (añadir al final) | `RFEVBPhaseParser`, `RFEVBTeamsParser` |
| `videosvoley/videos/management/commands/scrape_rfevb_fase.py` | Crear | Comando + función `scrape_rfevb_fases()` |
| `videosvoley/videos/tasks.py` | Modificar (añadir al final) | `scrape_rfevb_competition`, `scrape_rfevb_final_classification` |
| `videosvoley/videos/tests.py` | Modificar | Tests de parser, comando y tareas |

---

## Task 1: RFEVBPhaseParser y RFEVBTeamsParser

**Files:**
- Modify: `videosvoley/videos/scraping.py` (añadir al final, después de la clase `FederationScraper`)
- Modify: `videosvoley/videos/tests.py`

- [ ] **Step 1.1: Añadir fixture HTML y escribir tests fallidos del parser**

Reemplazar el contenido de `videosvoley/videos/tests.py`:

```python
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
        # Grupo A has 3 rows: match 1 (real, finished), match 2 (placeholder), match 3 (real, scheduled)
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
```

- [ ] **Step 1.2: Verificar que los tests fallan**

```bash
docker compose run --rm web python manage.py test videosvoley.videos -v 2
```

Resultado esperado: `ImportError: cannot import name 'RFEVBPhaseParser' from 'videosvoley.videos.scraping'`

- [ ] **Step 1.3: Implementar RFEVBPhaseParser y RFEVBTeamsParser en scraping.py**

Añadir al final de `videosvoley/videos/scraping.py` (después de la última línea existente `def parse_acta_lineup`):

```python


class RFEVBPhaseParser(BaseParser):
    """Parser para páginas de fase de campeonatos RFEVB.

    Parsea webCompeticion-campeonatosFase.php?auxIdFase=XXXX.
    Filtra automáticamente partidos con equipos placeholder (#= N Grupo X).
    """

    def parse_content(self, content: str) -> Dict[str, Any]:
        soup = BeautifulSoup(content, 'html.parser')
        groups = []

        for card in soup.find_all('div', class_='card'):
            h4 = card.find('h4')
            if not h4:
                continue
            group_name = h4.get_text(strip=True)

            tables = card.find_all('table')
            matches_table = next(
                (t for t in tables if 'table-responsive' in (t.get('class') or [])),
                None,
            )
            standings_table = next(
                (t for t in tables if t.get('width') == '80%'),
                None,
            )

            matches = self._parse_matches_table(matches_table) if matches_table else []
            standings = self._parse_standings_table(standings_table) if standings_table else []

            groups.append({'name': group_name, 'matches': matches, 'standings': standings})

        return {'groups': groups}

    def _parse_matches_table(self, table) -> List[Dict[str, Any]]:
        matches = []
        for row in table.find_all('tr'):
            th = row.find('th')
            if not th:
                continue
            try:
                match_number = int(th.get_text(strip=True))
            except ValueError:
                continue

            tds = row.find_all('td')
            if len(tds) < 4:
                continue

            teams_text = tds[0].get_text(strip=True)
            date_text = tds[1].get_text(strip=True)
            venue = tds[2].get_text(strip=True)
            score_text = tds[3].get_text(strip=True)

            parts = teams_text.split(' - ', 1)
            if len(parts) != 2:
                continue
            home_name, away_name = [p.strip() for p in parts]
            if home_name.startswith('#') or away_name.startswith('#'):
                continue

            try:
                match_date = datetime.strptime(date_text, '%d/%m/%y (%H:%M)')
                match_date = timezone.make_aware(match_date)
            except ValueError:
                logger.warning(f'RFEVB: fecha inválida {date_text!r} en partido {match_number}')
                continue

            score_parts = score_text.split(' - ')
            try:
                home_score = int(score_parts[0])
                away_score = int(score_parts[1])
            except (ValueError, IndexError):
                home_score, away_score = 0, 0

            if home_score == 0 and away_score == 0:
                status = 'scheduled'
                home_score = None
                away_score = None
            elif validate_volleyball_score(home_score, away_score, self.league):
                status = 'finished'
            else:
                logger.warning(
                    f'RFEVB: resultado inválido {home_score}-{away_score} en partido {match_number}'
                )
                status = 'scheduled'
                home_score = None
                away_score = None

            matches.append({
                'rfevb_match_number': match_number,
                'home_team_name': home_name,
                'away_team_name': away_name,
                'match_date': match_date,
                'venue': venue,
                'home_score': home_score,
                'away_score': away_score,
                'status': status,
            })

        return matches

    def _parse_standings_table(self, table) -> List[Dict[str, Any]]:
        standings = []
        tbody = table.find('tbody')
        if not tbody:
            return []

        for row in tbody.find_all('tr'):
            tds = row.find_all('td')
            if len(tds) < 11:
                continue
            try:
                position = int(tds[0].get_text(strip=True))
                team_name = tds[1].get_text(strip=True)
                total_points = int(tds[2].get_text(strip=True) or 0)
                played = int(tds[3].get_text(strip=True) or 0)
                g3 = int(tds[4].get_text(strip=True) or 0)
                g2 = int(tds[5].get_text(strip=True) or 0)
                p1 = int(tds[6].get_text(strip=True) or 0)
                p0 = int(tds[7].get_text(strip=True) or 0)
                sets_for = int(tds[8].get_text(strip=True) or 0)
                sets_against = int(tds[9].get_text(strip=True) or 0)
                points_for = int(tds[10].get_text(strip=True) or 0)
                points_against = int(tds[11].get_text(strip=True) or 0) if len(tds) > 11 else 0
            except (ValueError, IndexError) as e:
                logger.warning(f'RFEVB: error parseando fila de clasificación: {e}')
                continue

            standings.append({
                'position': position,
                'team_name': team_name,
                'total_points': total_points,
                'played': played,
                'won': g3 + g2,
                'lost': p1 + p0,
                'wins_3_0': g3,    # G3 agrupa victorias 3-0 y 3-1
                'wins_3_2': g2,
                'losses_2_3': p1,
                'losses_0_3': p0,  # P0 agrupa derrotas 0-3 y 1-3
                'sets_for': sets_for,
                'sets_against': sets_against,
                'points_for': points_for,
                'points_against': points_against,
            })

        return standings


class RFEVBTeamsParser(BaseParser):
    """Parser para la página de equipos participantes de una competición RFEVB.

    Parsea webCompeticion-equipos.php?IdCompeticion=XXXX.
    Devuelve {'teams': {nombre: logo_url}}.
    """

    def parse_content(self, content: str) -> Dict[str, Any]:
        soup = BeautifulSoup(content, 'html.parser')
        teams = {}

        table = soup.find('table', class_='table')
        if not table:
            return {'teams': {}}

        for row in table.find_all('tr'):
            tds = row.find_all('td')
            if len(tds) < 3:
                continue

            img = tds[1].find('img')
            logo_url = img.get('src', '') if img else ''

            raw_name = tds[2].get_text(strip=True)
            name = re.sub(r'\s*\([^)]+\)\s*$', '', raw_name).strip()

            if name and logo_url:
                teams[name] = logo_url

        return {'teams': teams}
```

- [ ] **Step 1.4: Ejecutar tests y verificar que pasan**

```bash
docker compose run --rm web python manage.py test videosvoley.videos -v 2
```

Resultado esperado:
```
test_all_placeholder_group_has_no_matches ... ok
test_finished_match_parsed_correctly ... ok
test_first_group_name ... ok
test_group_without_standings_has_empty_list ... ok
test_logo_url_extracted ... ok
test_match_date_parsed ... ok
test_placeholder_matches_filtered_out ... ok
test_region_stripped_from_name ... ok
test_returns_two_teams ... ok
test_scheduled_match_has_none_scores ... ok
test_second_group_name ... ok
test_standings_parsed_correctly ... ok
...
Ran 12 tests in X.XXXs
OK
```

- [ ] **Step 1.5: Commit**

```bash
git add videosvoley/videos/scraping.py videosvoley/videos/tests.py
git commit -m "feat(scraping): añadir RFEVBPhaseParser y RFEVBTeamsParser"
```

---

## Task 2: Comando scrape_rfevb_fase

**Files:**
- Create: `videosvoley/videos/management/commands/scrape_rfevb_fase.py`
- Modify: `videosvoley/videos/tests.py`

- [ ] **Step 2.1: Añadir tests del comando a tests.py**

Añadir al final de `videosvoley/videos/tests.py`:

```python
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
```

- [ ] **Step 2.2: Verificar que los tests fallan**

```bash
docker compose run --rm web python manage.py test videosvoley.videos.tests.ScrapeRFEVBFaseCommandTests -v 2
```

Resultado esperado: `CommandError` o `ModuleNotFoundError` — el comando no existe aún.

- [ ] **Step 2.3: Implementar el comando**

Crear `videosvoley/videos/management/commands/scrape_rfevb_fase.py`:

```python
import logging
import re
import time

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from unidecode import unidecode

from videosvoley.videos.models import League, Match, Standing, Team
from videosvoley.videos.scraping import RFEVBPhaseParser, RFEVBTeamsParser

logger = logging.getLogger(__name__)

RFEVB_BASE = 'https://intranet.rfevb.com/rfevbcom/includes-html/competiciones'


def scrape_rfevb_fases(competition_id, fase_ids, parent_league_id, dry_run=False, delay=2.0):
    """
    Función core de scraping RFEVB. Reutilizable desde el comando y desde tareas Celery.

    Returns dict con contadores: matches_found, created, updated, skipped, errors.
    """
    try:
        parent = League.objects.get(federation_id=parent_league_id)
    except League.DoesNotExist:
        logger.error(f'Liga padre no encontrada: {parent_league_id}')
        return {'error': f'Liga padre no encontrada: {parent_league_id}'}

    logo_map = _fetch_logo_map(competition_id, parent)
    team_map = _build_team_map()

    phase_parser = RFEVBPhaseParser(parent)
    totals = {'matches_found': 0, 'created': 0, 'updated': 0, 'skipped': 0, 'errors': []}

    for fase_id in fase_ids:
        url = f'{RFEVB_BASE}/webCompeticion-campeonatosFase.php?auxIdFase={fase_id}'
        try:
            content = phase_parser.fetch_content(url)
        except Exception as e:
            logger.error(f'Error fetching fase {fase_id}: {e}')
            totals['errors'].append(str(e))
            continue

        data = phase_parser.parse_content(content)

        for group in data['groups']:
            group_name = group['name']
            matches = group['matches']
            standings = group['standings']

            if not matches:
                logger.info(f'  {group_name}: todos placeholders, sin datos reales')
                continue

            sub_league = _get_or_create_subleague(parent, group_name, dry_run)
            if not sub_league:
                continue

            totals['matches_found'] += len(matches)

            for match_data in matches:
                result = _process_match(
                    match_data, sub_league, competition_id, team_map, logo_map, dry_run
                )
                totals[result] += 1

            if standings and not dry_run:
                _update_standings(standings, sub_league, team_map)

        if delay:
            time.sleep(delay)

    return totals


def _fetch_logo_map(competition_id, league):
    url = f'{RFEVB_BASE}/webCompeticion-equipos.php?IdCompeticion={competition_id}'
    parser = RFEVBTeamsParser(league)
    try:
        content = parser.fetch_content(url)
        return parser.parse_content(content).get('teams', {})
    except Exception as e:
        logger.warning(f'No se pudieron obtener logos: {e}')
        return {}


def _build_team_map():
    """Devuelve {nombre_normalizado: Team} con todos los equipos activos."""
    team_map = {}
    for team in Team.objects.filter(is_active=True):
        key = unidecode(team.name).lower().strip()
        team_map[key] = team
    return team_map


def _get_or_create_subleague(parent, group_name, dry_run):
    try:
        league = League.objects.get(
            parent_league=parent,
            phase_name=group_name,
            season=parent.season,
        )
        return league
    except League.DoesNotExist:
        pass

    if dry_run:
        logger.info(f'[DRY RUN] Se crearía sub-liga: {group_name}')
        return None

    fed_id = f'{parent.federation_id}_{slugify(group_name).replace("-", "_")}'
    try:
        league = League.objects.create(
            federation_id=fed_id,
            name=f'{parent.name} - {group_name}',
            season=parent.season,
            parent_league=parent,
            phase_name=group_name,
            competition_type=parent.competition_type,
            match_format=parent.match_format,
            visibility_type=parent.visibility_type,
            is_our_team_related=parent.is_our_team_related,
        )
        for cat in parent.categories.all():
            league.categories.add(cat)
        logger.info(f'Sub-liga creada: {league.name} ({fed_id})')
        return league
    except Exception as e:
        logger.error(f'Error creando sub-liga {group_name}: {e}')
        return None


def _resolve_team(name, team_map, logo_map, competition_id, dry_run):
    normalized = unidecode(name).lower().strip()
    team = team_map.get(normalized) or Team.objects.filter(name=name).first()

    if not team:
        logger.warning(f'Equipo no encontrado: {name!r}, creando...')
        if not dry_run:
            fed_id = f'rfevb_{competition_id}_{slugify(unidecode(name)).replace("-", "_")}'
            team, _ = Team.objects.get_or_create(
                federation_id=fed_id,
                defaults={'name': name, 'is_active': True},
            )
            team_map[normalized] = team

    if team and not team.logo_url and name in logo_map and not dry_run:
        team.logo_url = logo_map[name]
        team.save(update_fields=['logo_url'])

    return team


def _process_match(match_data, league, competition_id, team_map, logo_map, dry_run):
    home_team = _resolve_team(
        match_data['home_team_name'], team_map, logo_map, competition_id, dry_run
    )
    away_team = _resolve_team(
        match_data['away_team_name'], team_map, logo_map, competition_id, dry_run
    )

    if not home_team or not away_team:
        return 'skipped'

    rfevb_id = f'rfevb_{competition_id}_{match_data["rfevb_match_number"]}'

    if dry_run:
        return 'created'

    match = Match.objects.filter(federation_id=rfevb_id).first()
    created = False

    if not match:
        match = Match.objects.filter(
            league=league,
            home_team=home_team,
            away_team=away_team,
        ).first()
        if match:
            match.federation_id = rfevb_id
        else:
            match = Match(
                league=league,
                home_team=home_team,
                away_team=away_team,
                federation_id=rfevb_id,
                match_date=match_data['match_date'],
                venue=match_data.get('venue', ''),
                status='scheduled',
            )
            created = True

    if match_data['status'] == 'finished':
        match.home_score = match_data['home_score']
        match.away_score = match_data['away_score']
        match.status = 'finished'

    match.save()
    return 'created' if created else 'updated'


def _update_standings(standings, league, team_map):
    for s in standings:
        normalized = unidecode(s['team_name']).lower().strip()
        team = team_map.get(normalized) or Team.objects.filter(name=s['team_name']).first()
        if not team:
            logger.warning(f'Equipo no encontrado para clasificación: {s["team_name"]}')
            continue

        Standing.objects.update_or_create(
            league=league,
            team=team,
            defaults={
                'position': s['position'],
                'total_points': s['total_points'],
                'played': s['played'],
                'won': s['won'],
                'lost': s['lost'],
                'wins_3_0': s['wins_3_0'],
                'wins_3_2': s['wins_3_2'],
                'losses_2_3': s['losses_2_3'],
                'losses_0_3': s['losses_0_3'],
                'sets_for': s['sets_for'],
                'sets_against': s['sets_against'],
                'points_for': s['points_for'],
                'points_against': s['points_against'],
            },
        )


class Command(BaseCommand):
    help = 'Scraping de fases de campeonatos nacionales RFEVB'

    def add_arguments(self, parser):
        parser.add_argument('--competition-id', required=True, type=int,
                            dest='competition_id')
        parser.add_argument('--fase-ids', required=True, type=str,
                            dest='fase_ids',
                            help='IDs de fase separados por coma, ej: 2193,2194')
        parser.add_argument('--parent-league', required=True, type=str,
                            dest='parent_league',
                            help='federation_id de la liga padre, ej: ceim_2526')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run')
        parser.add_argument('--delay', type=float, default=2.0, dest='delay')

    def handle(self, *args, **options):
        fase_ids = [int(x.strip()) for x in options['fase_ids'].split(',')]

        if options['dry_run']:
            self.stdout.write('[DRY RUN] No se guardarán cambios')

        result = scrape_rfevb_fases(
            competition_id=options['competition_id'],
            fase_ids=fase_ids,
            parent_league_id=options['parent_league'],
            dry_run=options['dry_run'],
            delay=options['delay'],
        )

        if 'error' in result:
            self.stderr.write(self.style.ERROR(result['error']))
            return

        self.stdout.write(self.style.SUCCESS(
            f"\nRESUMEN: {len(fase_ids)} fases | "
            f"{result['matches_found']} partidos | "
            f"{result.get('created', 0)} creados | "
            f"{result.get('updated', 0)} actualizados | "
            f"{result.get('skipped', 0)} omitidos | "
            f"{len(result['errors'])} errores"
        ))
```

- [ ] **Step 2.4: Ejecutar tests y verificar que pasan**

```bash
docker compose run --rm web python manage.py test videosvoley.videos -v 2
```

Resultado esperado: todos los tests OK (12 de parsers + 9 del comando = 21 total).

- [ ] **Step 2.5: Smoke test manual con dry-run**

```bash
docker compose run --rm web python manage.py scrape_rfevb_fase \
  --competition-id 9041 \
  --fase-ids 2193,2194,2195,2196 \
  --parent-league ceim_2526 \
  --dry-run
```

Resultado esperado: output sin errores mostrando grupos y contadores (todos 0 en dry-run).

- [ ] **Step 2.6: Commit**

```bash
git add videosvoley/videos/management/commands/scrape_rfevb_fase.py videosvoley/videos/tests.py
git commit -m "feat(commands): añadir scrape_rfevb_fase para campeonatos nacionales"
```

---

## Task 3: Tareas Celery

**Files:**
- Modify: `videosvoley/videos/tasks.py` (añadir al final)
- Modify: `videosvoley/videos/tests.py`

- [ ] **Step 3.1: Añadir tests de las tareas Celery a tests.py**

Añadir al final de `videosvoley/videos/tests.py`:

```python
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
```

- [ ] **Step 3.2: Verificar que los tests fallan**

```bash
docker compose run --rm web python manage.py test videosvoley.videos.tests.ScrapeRFEVBCompetitionTaskTests -v 2
```

Resultado esperado: `ImportError: cannot import name 'scrape_rfevb_competition' from 'videosvoley.videos.tasks'`

- [ ] **Step 3.3: Implementar las tareas en tasks.py**

Añadir el import de `scrape_rfevb_fases` en la sección de imports de `videosvoley/videos/tasks.py` (junto a los imports existentes, línea ~16):

```python
from videosvoley.videos.management.commands.scrape_rfevb_fase import scrape_rfevb_fases
```

Luego añadir al final del fichero:

```python
# ---------------------------------------------------------------------------
# Scraping RFEVB — Campeonatos Nacionales
# ---------------------------------------------------------------------------

@shared_task(name='scrape_rfevb_competition', bind=False)
def scrape_rfevb_competition(competition_id, fase_ids, parent_league_id):
    """
    Scraping de todas las fases de un campeonato RFEVB.

    Tras el scraping, si no quedan partidos pendientes bajo la liga padre,
    lanza scrape_rfevb_final_classification para cargar la clasificación general.

    Uso:
        scrape_rfevb_competition.delay(9041, [2193, 2194, 2195, 2196], 'ceim_2526')
    """
    result = scrape_rfevb_fases(competition_id, fase_ids, parent_league_id)
    logger.info(f'RFEVB scraping completado: {result}')

    try:
        parent = League.objects.get(federation_id=parent_league_id)
        pending = Match.objects.filter(
            league__parent_league=parent,
            status='scheduled',
        ).exists()
        if not pending:
            logger.info('Todos los partidos finalizados, lanzando clasificación final')
            scrape_rfevb_final_classification.delay(competition_id, parent_league_id)
    except League.DoesNotExist:
        logger.error(f'Liga padre no encontrada para trigger final: {parent_league_id}')

    return result


@shared_task(name='scrape_rfevb_final_classification', bind=False)
def scrape_rfevb_final_classification(competition_id, parent_league_id):
    """
    Scraping de la clasificación general final de una competición RFEVB.

    Parsea webCompeticion-clasificacion.php?IdCompeticion={id}.
    Se activa automáticamente desde scrape_rfevb_competition cuando todos
    los partidos están finalizados.

    NOTA: El parser de clasificación final se implementará cuando el torneo
    tenga datos reales (la página devuelve vacío antes de que termine).
    Por ahora registra la intención en el log.
    """
    logger.info(
        f'RFEVB clasificación final pendiente de implementar: '
        f'competition_id={competition_id}, parent_league={parent_league_id}'
    )
    # TODO: implementar cuando webCompeticion-clasificacion.php tenga datos reales
    # URL: {RFEVB_BASE}/webCompeticion-clasificacion.php?IdCompeticion={competition_id}
```

> **Nota sobre el stub:** `scrape_rfevb_final_classification` es un stub deliberado. La página de clasificación general devuelve HTML vacío antes de que termine el torneo. Se completa en el torneo con la URL real y el parser correspondiente.

- [ ] **Step 3.4: Añadir import de Match en tasks.py si no está**

Verificar que `Match` está importado en `videosvoley/videos/tasks.py` (línea ~14):

```python
from videosvoley.videos.models import League, Club, Team, Match
```

Si no incluye `Match`, añadirlo.

- [ ] **Step 3.5: Ejecutar todos los tests**

```bash
docker compose run --rm web python manage.py test videosvoley.videos -v 2
```

Resultado esperado: todos los tests OK (12 parsers + 9 comando + 3 tareas = 24 total).

- [ ] **Step 3.6: Commit final**

```bash
git add videosvoley/videos/tasks.py videosvoley/videos/tests.py
git commit -m "feat(tasks): añadir tareas Celery scrape_rfevb_competition y stub clasificación final"
```

---

## Uso durante el CEIM 2025-26 (27-30 mayo)

**Ejecución manual:**
```bash
docker compose run --rm web python manage.py scrape_rfevb_fase \
  --competition-id 9041 \
  --fase-ids 2193,2194,2195,2196 \
  --parent-league ceim_2526
```

**Lanzar tarea Celery manualmente desde shell Django:**
```python
from videosvoley.videos.tasks import scrape_rfevb_competition
scrape_rfevb_competition.delay(9041, [2193, 2194, 2195, 2196], 'ceim_2526')
```

**Verificación sin cambios:**
```bash
docker compose run --rm web python manage.py scrape_rfevb_fase \
  --competition-id 9041 \
  --fase-ids 2193 \
  --parent-league ceim_2526 \
  --dry-run
```
