from django.core.management.base import BaseCommand, CommandError

from ilovevoley.competitions.services.discovery import discover, discover_seasonal_beach
from ilovevoley.core.models import Season


class Command(BaseCommand):
    help = 'Descubre ligas nuevas en el menú de voleibolib y las deja pendientes de validar en el admin.'

    def add_arguments(self, parser):
        parser.add_argument('--season', help='Temporada, ej. 2026-27 (por defecto la activa)')
        parser.add_argument(
            '--seasonal', '--beach',
            action='store_true',
            dest='seasonal',
            help='Descubre competiciones de vóley playa en la ventana estacional de verano.',
        )
        parser.add_argument(
            '--date-range',
            nargs=2,
            metavar=('FINI', 'FFIN'),
            help='Rango de fechas para el desglose estacional (DD/MM/YYYY DD/MM/YYYY)',
        )

    def handle(self, *args, **options):
        season = Season.objects.resolve(options['season']) if options['season'] else Season.objects.current()
        if season is None:
            raise CommandError('Temporada no válida o inexistente.')
        if options.get('seasonal') or options.get('date_range'):
            fini, ffin = options['date_range'] if options.get('date_range') else (None, None)
            candidates = discover_seasonal_beach(season, fini=fini, ffin=ffin)
        else:
            candidates = discover(season)
        for candidate in candidates:
            self.stdout.write(f'{candidate.federation_id}  {candidate.category_label} · {candidate.phase_label}  {candidate.matched_teams}')
        self.stdout.write(self.style.SUCCESS(f'{len(candidates)} candidatas nuevas en {season}.'))

