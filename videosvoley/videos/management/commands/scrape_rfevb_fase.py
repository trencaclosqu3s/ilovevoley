import logging
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
