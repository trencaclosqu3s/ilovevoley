from django.core.management.base import BaseCommand, CommandError
from videosvoley.core.models import Season
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
        parser.add_argument(
            '--match-format',
            type=str,
            choices=['standard', 'alevin_balear', 'tournament_3sets', 'custom'],
            default='standard',
            help='Formato de partido para esta liga'
        )
        parser.add_argument(
            '--custom-max-sets',
            type=int,
            help='Máximo de sets (solo si formato es personalizado)'
        )
        parser.add_argument(
            '--custom-sets-to-win',
            type=int,
            help='Sets necesarios para ganar (solo si formato es personalizado)'
        )

    def handle(self, *args, **options):
        name = options['name']
        federation_id = options['federation_id']
        season = Season.objects.resolve(options['season'])
        competition_type = options['competition_type']
        base_url = options['base_url']
        match_format = options['match_format']
        custom_max_sets = options.get('custom_max_sets')
        custom_sets_to_win = options.get('custom_sets_to_win')

        # Validar parámetros personalizados
        if match_format == 'custom':
            if not custom_max_sets or not custom_sets_to_win:
                self.stdout.write(
                    self.style.ERROR('Para formato personalizado, debes especificar --custom-max-sets y --custom-sets-to-win')
                )
                return
        
        # Crear o actualizar la liga
        league_data = {
            'name': name,
            'competition_type': competition_type,
            'base_url': base_url,
            'match_format': match_format,
            'is_active': True
        }
        
        if match_format == 'custom':
            league_data['custom_max_sets'] = custom_max_sets
            league_data['custom_sets_to_win'] = custom_sets_to_win
        
        league, created = League.objects.get_or_create(
            federation_id=federation_id,
            season=season,
            defaults=league_data
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Liga creada: {league.name} (formato: {league.get_match_format_display()})')
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