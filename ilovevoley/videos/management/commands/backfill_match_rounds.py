import logging

from django.core.management.base import BaseCommand, CommandError

from ilovevoley.videos.models import League, Match
from ilovevoley.videos.scraping import FederationScraper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Corrige round_number de partidos importados del JSON (que asignaba 1) '
        'cruzando club local/visitante con el HTML de resultados de cada jornada (#369)'
    )

    def add_arguments(self, parser):
        parser.add_argument('--league-id', type=str, help='federation_id de una sola liga')
        parser.add_argument('--dry-run', action='store_true', help='Muestra los cambios sin guardarlos')
        parser.add_argument('--delay', type=float, default=1.0, help='Segundos entre peticiones')

    def handle(self, *args, **options):
        leagues = League.objects.filter(is_active=True, federation_id__regex=r'^\d+$')
        if options['league_id']:
            leagues = leagues.filter(federation_id=options['league_id'])
            if not leagues:
                raise CommandError(f'Liga {options["league_id"]} no encontrada, inactiva o sin id numérico')

        total = 0
        for league in leagues:
            round_map = FederationScraper(league)._fetch_round_map(league, delay=options['delay'])
            matches = Match.all_objects.filter(league=league, is_friendly=False).select_related(
                'home_team__club', 'away_team__club'
            )
            changed = unresolved = 0
            for match in matches:
                home_club, away_club = match.home_team.club, match.away_team.club
                round_number = home_club and away_club and round_map.get(
                    (home_club.federation_id, away_club.federation_id)
                )
                if not round_number:
                    unresolved += 1
                elif round_number != match.round_number:
                    changed += 1
                    if not options['dry_run']:
                        # update() y no save(): no debe disparar avisos de partido
                        Match.all_objects.filter(pk=match.pk).update(round_number=round_number)
            total += changed
            self.stdout.write(
                f'{league.federation_id} {league.name}: {changed} corregidos, '
                f'{unresolved} sin resolver, {len(round_map)} cruces en la federación'
            )

        suffix = ' (dry-run, nada guardado)' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(f'Total corregidos: {total}{suffix}'))
