from django.core.management.base import BaseCommand

from ilovevoley.core.models import Season
from ilovevoley.videos.models import Category, League

SEASON = '2025-26'


class Command(BaseCommand):
    help = 'Crea la liga padre del CESA 2025-26 (Infantil). Los grupos y partidos se importan con scrape_rfevb_fase.'

    def handle(self, *args, **options):
        category = Category.objects.get(id=1)  # Infantil
        season = Season.objects.resolve(SEASON)

        league, created = League.objects.get_or_create(
            federation_id='cesa_2526',
            defaults={
                'name': 'CESA 2025-26 - Campeonato de España de Selecciones Autonómicas Infantil',
                'season': season,
                'competition_type': 'cup',
                'match_format': 'standard',
                'visibility_type': 'main',
                'is_our_team_related': True,
            },
        )
        league.categories.add(category)

        label = 'CREADA' if created else 'ya existía'
        self.stdout.write(self.style.SUCCESS(
            f'Liga padre [{label}]: {league.name} (federation_id: {league.federation_id})'
        ))
        self.stdout.write(
            'Siguiente paso:\n'
            '  docker compose run --rm web python manage.py scrape_rfevb_fase \\\n'
            '    --competition-id 9086 \\\n'
            '    --fase-ids 2240,2241,2242,2243 \\\n'
            '    --parent-league cesa_2526'
        )
