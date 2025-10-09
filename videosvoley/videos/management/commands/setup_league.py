from django.core.management.base import BaseCommand, CommandError
from videosvoley.videos.models import League, ScrapingEndpoint


class Command(BaseCommand):
    help = 'Configura una nueva liga con endpoints básicos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name',
            type=str,
            required=True,
            help='Nombre de la liga'
        )
        parser.add_argument(
            '--federation-id',
            type=str,
            required=True,
            help='ID de la federación (usado en las URLs)'
        )
        parser.add_argument(
            '--season',
            type=str,
            required=True,
            help='Temporada (ej: 2024-25)'
        )
        parser.add_argument(
            '--competition-type',
            type=str,
            choices=['regular', 'playoff', 'cup', 'friendly'],
            default='regular',
            help='Tipo de competición'
        )
        parser.add_argument(
            '--base-url',
            type=str,
            default='https://www.voleibolib.net',
            help='URL base del sitio de la federación'
        )

    def handle(self, *args, **options):
        name = options['name']
        federation_id = options['federation_id']
        season = options['season']
        competition_type = options['competition_type']
        base_url = options['base_url']

        # Crear o actualizar la liga
        league, created = League.objects.get_or_create(
            federation_id=federation_id,
            season=season,
            defaults={
                'name': name,
                'competition_type': competition_type,
                'base_url': base_url,
                'is_active': True
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Liga creada: {league.name}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Liga ya existe: {league.name}')
            )

        # Crear endpoints básicos si no existen
        endpoints_config = [
            {
                'endpoint_type': 'standings',
                'url_pattern': 'JSON/get_clasificacion.asp?id={league_id}',
                'parser_type': 'table_standings'
            },
            {
                'endpoint_type': 'results',
                'url_pattern': 'JSON/get_resultados.asp?id={league_id}&jor={round}',
                'parser_type': 'match_results'
            },
            {
                'endpoint_type': 'calendar',
                'url_pattern': 'JSON/get_calendario.asp?id={league_id}',
                'parser_type': 'match_calendar'
            }
        ]

        for endpoint_config in endpoints_config:
            endpoint, created = ScrapingEndpoint.objects.get_or_create(
                league=league,
                endpoint_type=endpoint_config['endpoint_type'],
                defaults=endpoint_config
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Endpoint creado: {endpoint.get_endpoint_type_display()}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Endpoint ya existe: {endpoint.get_endpoint_type_display()}'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Liga {league.name} configurada correctamente.\n'
                f'Para hacer scraping ejecuta:\n'
                f'python manage.py scrape_league --league-id {federation_id}'
            )
        )