"""Backfill del JSON de actas y de las alineaciones por partido.

Recorre los partidos que tienen ``acta_html`` pero aún no tienen ``acta_data``,
descarga y parsea el acta y persiste tanto el JSON como las filas de
``MatchLineup``. Es una operación de red: se lanza a mano para poblar el
histórico de partidos anteriores a la funcionalidad.

Uso:
    python manage.py backfill_acta_lineups [--league ID] [--limit N] [--force] [--dry-run]
"""

import requests
from django.conf import settings

from django.core.management.base import BaseCommand

from ilovevoley.core.security import UnsafeURL, safe_get
from ilovevoley.videos.scraping import parse_acta_lineup

from ...models import Match
from ...services.lineups import store_match_lineups


class Command(BaseCommand):
    help = 'Parsea y persiste las actas federativas pendientes para el histórico por jugador.'

    def add_arguments(self, parser):
        parser.add_argument('--league', type=int, help='Limita a una liga concreta')
        parser.add_argument('--limit', type=int, help='Número máximo de actas a procesar')
        parser.add_argument(
            '--force', action='store_true',
            help='Reprocesa también los partidos que ya tienen acta_data',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Lista los partidos a procesar sin descargar ni guardar',
        )

    def handle(self, *args, **options):
        matches = Match.all_objects.exclude(acta_html='').exclude(acta_html__isnull=True).select_related(
            'home_team', 'away_team', 'league__season'
        )
        if options.get('league'):
            matches = matches.filter(league_id=options['league'])
        if not options['force']:
            matches = matches.filter(acta_data__isnull=True)
        matches = matches.order_by('match_date')
        if options.get('limit'):
            matches = matches[:options['limit']]

        matches = list(matches)
        if not matches:
            self.stdout.write('No hay actas pendientes de procesar.')
            return

        if options['dry_run']:
            for match in matches:
                self.stdout.write(f'[dry-run] {match.id}: {match.acta_html}')
            self.stdout.write(f'{len(matches)} partidos pendientes.')
            return

        ok = 0
        failed = 0
        for match in matches:
            acta_url = match.official_acta_url or match.acta_html
            try:
                content = safe_get(
                    acta_url, allowed_hosts=settings.ACTA_ALLOWED_HOSTS,
                )
                lineup_data = parse_acta_lineup(content)
                store_match_lineups(match, lineup_data)
                ok += 1
                self.stdout.write(f'OK {match.id}: {acta_url}')
            except UnsafeURL as e:
                failed += 1
                self.stderr.write(f'DESCARTADO {match.id}: {e}')
            except (requests.exceptions.RequestException, ValueError) as e:
                failed += 1
                self.stderr.write(f'ERROR {match.id}: {e}')

        self.stdout.write(self.style.SUCCESS(
            f'Procesadas {ok} actas, {failed} con error.'
        ))
