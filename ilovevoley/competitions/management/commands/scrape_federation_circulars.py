from django.core.management.base import BaseCommand, CommandError

from ilovevoley.core.models import Season
from ilovevoley.competitions.models import FederationCircular
from ilovevoley.competitions.services.circulars_ingestion import DEFAULT_TIPOS, run_circulars_scrape


class Command(BaseCommand):
    help = "Indexa circulares federativas (FVBIB): comité de competición, normas y vóley playa por defecto."

    def add_arguments(self, parser):
        parser.add_argument('--season', type=str, help="Nombre de la temporada (ej: '2026-27'). Por defecto la activa.")
        parser.add_argument('--temp', type=str, help="Parámetro de temporada de voleibolib (ej: '2627').")
        parser.add_argument(
            '--tipo',
            type=int,
            action='append',
            choices=[t for t, _label in FederationCircular.TIPO_CHOICES],
            help="Tipo de circular; repetible. Por defecto 6 (comité de competición), 11 (normas) y 8 (vóley playa).",
        )
        parser.add_argument('--dry-run', action='store_true', help="Cuenta circulares nuevas sin guardar.")

    def handle(self, *args, **options):
        if options['season']:
            try:
                season = Season.objects.get(name=options['season'])
            except Season.DoesNotExist:
                raise CommandError(f"No existe la temporada '{options['season']}'.")
        else:
            season = Season.objects.current()
        result = run_circulars_scrape(
            season,
            tipos=options['tipo'] or DEFAULT_TIPOS,
            temp=options['temp'],
            dry_run=options['dry_run'],
        )
        self.stdout.write(
            self.style.SUCCESS(f"Circulares nuevas: {result['created']}, ya existentes: {result['existing']}, "
                f"filas de sanciones guardadas: {result['sanctions']}.")
        )
