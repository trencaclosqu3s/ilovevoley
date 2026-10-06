from django.core.management.base import BaseCommand, CommandError

from ilovevoley.competitions.services.discovery import discover
from ilovevoley.core.models import Season


class Command(BaseCommand):
    help = 'Descubre ligas nuevas en el menú de voleibolib y las deja pendientes de validar en el admin.'

    def add_arguments(self, parser):
        parser.add_argument('--season', help='Temporada, ej. 2026-27 (por defecto la activa)')

    def handle(self, *args, **options):
        season = Season.objects.resolve(options['season']) if options['season'] else Season.objects.current()
        if season is None:
            raise CommandError('Temporada no válida o inexistente.')
        candidates = discover(season)
        for candidate in candidates:
            self.stdout.write(f'{candidate.federation_id}  {candidate.category_label} · {candidate.phase_label}  {candidate.matched_teams}')
        self.stdout.write(self.style.SUCCESS(f'{len(candidates)} candidatas nuevas en {season}.'))
