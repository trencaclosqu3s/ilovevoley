"""
Scraping de campeonatos nacionales RFEVB.

Función core reutilizable desde el comando scrape_rfevb_fase y desde tareas Celery.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup
from django.utils.text import slugify
from unidecode import unidecode

from videosvoley.videos.models import League, Match, ScrapingEndpoint, Standing, Team
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

            try:
                sub_league = _get_or_create_subleague(parent, group_name, dry_run)
            except Exception as e:
                totals['errors'].append(f'Error creando sub-liga {group_name}: {e}')
                continue
            if not sub_league:
                continue

            totals['matches_found'] += len(matches)

            # Pre-load existing matches to avoid N+1 SELECTs per iteration
            existing_by_fed_id = {m.federation_id: m for m in Match.all_objects.filter(league=sub_league)}
            existing_by_teams = {(m.home_team_id, m.away_team_id): m for m in existing_by_fed_id.values()}

            to_create = []
            to_update = []
            for match_data in matches:
                result, match_obj = _process_match(
                    match_data, sub_league, competition_id, team_map, logo_map, dry_run,
                    existing_by_fed_id, existing_by_teams,
                )
                totals[result] += 1
                if match_obj:
                    (to_create if result == 'created' else to_update).append(match_obj)

            if not dry_run:
                if to_create:
                    Match.objects.bulk_create(to_create)
                if to_update:
                    Match.objects.bulk_update(
                        to_update, ['federation_id', 'home_score', 'away_score', 'status']
                    )

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
        # La señal crea endpoints de voleibolib.net por defecto, pero las sub-ligas
        # RFEVB no usan ese scraper — desactivarlos para evitar errores 500.
        ScrapingEndpoint.objects.filter(league=league).update(is_active=False)
        logger.info(f'Sub-liga creada: {league.name} ({fed_id})')
        return league
    except Exception as e:
        logger.error(f'Error creando sub-liga {group_name}: {e}')
        raise


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


def _process_match(match_data, league, competition_id, team_map, logo_map, dry_run,
                   existing_by_fed_id=None, existing_by_teams=None):
    home_team = _resolve_team(
        match_data['home_team_name'], team_map, logo_map, competition_id, dry_run
    )
    away_team = _resolve_team(
        match_data['away_team_name'], team_map, logo_map, competition_id, dry_run
    )

    if not home_team or not away_team:
        return 'skipped', None

    rfevb_id = f'rfevb_{competition_id}_{match_data["rfevb_match_number"]}'

    if dry_run:
        if existing_by_fed_id is not None:
            exists = rfevb_id in existing_by_fed_id or (home_team.id, away_team.id) in existing_by_teams
        else:
            exists = (
                Match.objects.filter(federation_id=rfevb_id).exists()
                or Match.objects.filter(league=league, home_team=home_team, away_team=away_team).exists()
            )
        return ('updated' if exists else 'created'), None

    match = (existing_by_fed_id or {}).get(rfevb_id)
    needs_save = False
    created = False

    if not match:
        match = (existing_by_teams or {}).get((home_team.id, away_team.id))
        if match:
            match.federation_id = rfevb_id
            needs_save = True
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
            needs_save = True

    if match_data['status'] == 'finished':
        match.home_score = match_data['home_score']
        match.away_score = match_data['away_score']
        match.status = 'finished'
        needs_save = True

    return ('created' if created else 'updated'), (match if needs_save else None)


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
                'wins_3_0': s.get('wins_3_0', 0),
                'wins_3_1': s.get('wins_3_1', 0),
                'wins_3_2': s.get('wins_3_2', 0),
                'losses_2_3': s.get('losses_2_3', 0),
                'losses_1_3': s.get('losses_1_3', 0),
                'losses_0_3': s.get('losses_0_3', 0),
                'sets_for': s['sets_for'],
                'sets_against': s['sets_against'],
                'points_for': s['points_for'],
                'points_against': s['points_against'],
            },
        )


def scrape_rfevb_final_classification(competition_id, parent_league_id):
    """
    Parsea webCompeticion-clasificacion.php?IdCompeticion=X y guarda la
    clasificación final en una sub-liga 'Clasificación Final' bajo el padre.
    """
    try:
        parent = League.objects.get(federation_id=parent_league_id)
    except League.DoesNotExist:
        logger.error(f'Liga padre no encontrada: {parent_league_id}')
        return {'error': f'Liga padre no encontrada: {parent_league_id}'}

    url = f'{RFEVB_BASE}/webCompeticion-clasificacion.php?IdCompeticion={competition_id}'
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except Exception as e:
        logger.error(f'Error fetching clasificación final: {e}')
        return {'error': str(e)}

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table')
    if not table:
        logger.warning('Clasificación final: no se encontró tabla')
        return {'error': 'tabla no encontrada'}

    rankings = []
    for row in table.find_all('tr'):
        tds = row.find_all('td')
        if len(tds) < 3:
            continue
        try:
            position = int(tds[0].get_text(strip=True))
        except ValueError:
            continue
        raw_name = tds[2].get_text(strip=True)
        team_name = re.sub(r'\s*\([^)]+\)\s*$', '', raw_name).strip()
        if team_name:
            rankings.append({'position': position, 'team_name': team_name})

    if not rankings:
        logger.warning('Clasificación final: sin datos en la tabla')
        return {'error': 'sin datos'}

    fed_id = f'{parent_league_id}_clasificacion_final'
    ranking_league, _ = League.objects.get_or_create(
        federation_id=fed_id,
        defaults={
            'name': f'{parent.name} - Clasificación Final',
            'season': parent.season,
            'parent_league': parent,
            'phase_name': 'Clasificación Final',
            'competition_type': parent.competition_type,
            'match_format': parent.match_format,
            'visibility_type': parent.visibility_type,
            'is_our_team_related': parent.is_our_team_related,
        },
    )
    for cat in parent.categories.all():
        ranking_league.categories.add(cat)

    team_map = {unidecode(t.name).lower().strip(): t for t in Team.objects.filter(is_active=True)}

    saved = 0
    for entry in rankings:
        key = unidecode(entry['team_name']).lower().strip()
        team = team_map.get(key) or Team.objects.filter(name=entry['team_name']).first()
        if not team:
            logger.warning(f'Clasificación final: equipo no encontrado: {entry["team_name"]!r}')
            continue
        Standing.objects.update_or_create(
            league=ranking_league,
            team=team,
            defaults={
                'position': entry['position'],
                'total_points': 0, 'played': 0, 'won': 0, 'lost': 0,
                'sets_for': 0, 'sets_against': 0,
                'points_for': 0, 'points_against': 0,
            },
        )
        saved += 1

    logger.info(f'Clasificación final guardada: {saved}/{len(rankings)} equipos en {ranking_league.name}')
    return {'saved': saved, 'total': len(rankings)}
