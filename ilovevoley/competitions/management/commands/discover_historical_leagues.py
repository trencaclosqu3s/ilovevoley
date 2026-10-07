from django.core.management.base import BaseCommand, CommandError

from ilovevoley.competitions.services.discovery import discover_historical
from ilovevoley.core.models import Season


class Command(BaseCommand):
    help = (
        'Propone ligas históricas de categorías base (Alevín, Infantil, Cadete y '
        'Juvenil) de temporadas pasadas como candidatas pendientes de validar (#404). '
        'No crea ligas: se aprueban y sincronizan desde el admin.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--seasons', type=int, default=5,
            help='Número de temporadas anteriores a revisar (por defecto 5).',
        )
        parser.add_argument(
            '--season',
            help='Temporada base (por defecto la activa); se revisan las N anteriores.',
        )

    def handle(self, *args, **options):
        base = Season.objects.resolve(options['season']) if options['season'] else Season.objects.current()
        if base is None:
            raise CommandError('Temporada no válida o inexistente.')

        seasons = [
            Season.objects.resolve(f'{base.start_year - i}-{base.start_year - i + 1}')
            for i in range(1, options['seasons'] + 1)
        ]
        candidates = discover_historical(seasons)
        for candidate in candidates:
            self.stdout.write(
                f'{candidate.federation_id}  {candidate.category_label} · '
                f'{candidate.phase_label}  ({candidate.season})  {candidate.matched_teams}'
            )
        self.stdout.write(self.style.SUCCESS(f'{len(candidates)} candidatas históricas nuevas.'))
