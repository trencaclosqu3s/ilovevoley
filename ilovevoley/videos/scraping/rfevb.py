"""Parsers para campeonatos y fases RFEVB."""

from datetime import datetime
import logging
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup
from django.utils import timezone

from .base import BaseParser, validate_volleyball_score

logger = logging.getLogger(__name__)


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

            score_parts = score_text.split(' - ', 1)
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
            if len(tds) < 12:
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
                points_against = int(tds[11].get_text(strip=True) or 0)
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

__all__ = [
    'RFEVBPhaseParser',
    'RFEVBTeamsParser',
]
