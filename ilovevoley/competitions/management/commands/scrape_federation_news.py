from django.core.management.base import BaseCommand

from ilovevoley.competitions.services.news_ingestion import run_news_scrape


class Command(BaseCommand):
    help = "Sincroniza las noticias federativas (FVBIB): metadatos y enlace a la web oficial."

    def add_arguments(self, parser):
        parser.add_argument('--pages', type=int, default=5, help="Páginas de 100 noticias como máximo (por defecto 5).")

        parser.add_argument(
            '--full',
            action='store_true',
            help="Recorre todas las páginas aunque no haya novedades (retomar un backfill interrumpido).",
        )

    def handle(self, *args, **options):
        result = run_news_scrape(max_pages=options['pages'], full=options['full'])
        self.stdout.write(self.style.SUCCESS(f"Noticias nuevas: {result['created']}."))
