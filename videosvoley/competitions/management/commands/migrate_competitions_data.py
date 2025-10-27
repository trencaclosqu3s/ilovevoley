from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from videosvoley.videos.models import League as OldLeague, Match as OldMatch, Standing as OldStanding, ScrapingEndpoint as OldScrapingEndpoint
from videosvoley.competitions.models import League as NewLeague, Match as NewMatch, Standing as NewStanding, ScrapingEndpoint as NewScrapingEndpoint

class Command(BaseCommand):
    help = 'Migra datos de competitions desde la app videos a la nueva app competitions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular migración sin hacer cambios reales',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Tamaño del lote para procesar (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        self.stdout.write(
            self.style.SUCCESS('Iniciando migración de datos de competitions...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se realizarán cambios reales')
            )
        
        try:
            with transaction.atomic():
                # Migrar ligas
                self.migrate_leagues(dry_run, batch_size)
                
                # Migrar endpoints de scraping
                self.migrate_scraping_endpoints(dry_run, batch_size)
                
                # Migrar partidos
                self.migrate_matches(dry_run, batch_size)
                
                # Migrar clasificaciones
                self.migrate_standings(dry_run, batch_size)
                
                if dry_run:
                    # En dry-run, hacer rollback
                    raise Exception("Dry run - rollback")
                
                self.stdout.write(
                    self.style.SUCCESS('Migración completada exitosamente!')
                )
                
        except Exception as e:
            if not dry_run:
                self.stdout.write(
                    self.style.ERROR(f'Error durante la migración: {e}')
                )
                raise
            else:
                self.stdout.write(
                    self.style.SUCCESS('Dry run completado - no se realizaron cambios')
                )

    def migrate_leagues(self, dry_run, batch_size):
        """Migrar ligas"""
        self.stdout.write('Migrando ligas...')
        
        old_leagues = OldLeague.objects.all()
        total = old_leagues.count()
        
        if total == 0:
            self.stdout.write('No hay ligas para migrar')
            return
        
        self.stdout.write(f'Encontradas {total} ligas')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_leagues[i:i + batch_size]
                for old_league in batch:
                    # Obtener nueva categoría
                    new_category = None
                    if old_league.category:
                        try:
                            from videosvoley.content.models import Category
                            new_category = Category.objects.get(name=old_league.category.name)
                        except Category.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Categoría no encontrada: {old_league.category.name}')
                            )
                    
                    try:
                        league, created = NewLeague.objects.update_or_create(
                            id=old_league.id,  # Mantener mismo ID
                            defaults={
                                'name': old_league.name,
                                'federation_id': old_league.federation_id,
                                'competition_type': old_league.competition_type,
                                'season': old_league.season,
                                'category': new_category,
                                'is_active': old_league.is_active,
                                'visibility_type': old_league.visibility_type,
                                'is_historical': old_league.is_historical,
                                'is_our_team_related': old_league.is_our_team_related,
                                'match_format': old_league.match_format,
                                'custom_max_sets': old_league.custom_max_sets,
                                'custom_sets_to_win': old_league.custom_sets_to_win,
                                'base_url': old_league.base_url,
                                'created_at': old_league.created_at,
                            }
                        )
                        if created:
                            self.stdout.write(f'Nueva liga creada: {league.name}')
                        else:
                            self.stdout.write(f'Liga actualizada: {league.name}')
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error migrando liga {old_league.id}: {e}')
                        )
                self.stdout.write(f'Procesadas {min(i + batch_size, total)} ligas')
        
        self.stdout.write(
            self.style.SUCCESS(f'Ligas migradas: {total}')
        )

    def migrate_scraping_endpoints(self, dry_run, batch_size):
        """Migrar endpoints de scraping"""
        self.stdout.write('Migrando endpoints de scraping...')
        
        old_endpoints = OldScrapingEndpoint.objects.select_related('league').all()
        total = old_endpoints.count()
        
        if total == 0:
            self.stdout.write('No hay endpoints para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} endpoints')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_endpoints[i:i + batch_size]
                for old_endpoint in batch:
                    # Obtener nueva liga
                    try:
                        new_league = NewLeague.objects.get(id=old_endpoint.league.id)
                    except NewLeague.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Liga no encontrada: {old_endpoint.league.id}')
                        )
                        continue
                    
                    try:
                        endpoint, created = NewScrapingEndpoint.objects.update_or_create(
                            id=old_endpoint.id,  # Mantener mismo ID
                            defaults={
                                'league': new_league,
                                'endpoint_type': old_endpoint.endpoint_type,
                                'url_pattern': old_endpoint.url_pattern,
                                'parser_type': old_endpoint.parser_type,
                                'is_active': old_endpoint.is_active,
                                'extra_params': old_endpoint.extra_params,
                                'created_at': old_endpoint.created_at,
                            }
                        )
                        if created:
                            self.stdout.write(f'Nuevo endpoint creado: {endpoint.id} - {endpoint.endpoint_type}')
                        else:
                            self.stdout.write(f'Endpoint actualizado: {endpoint.id} - {endpoint.endpoint_type}')
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error creando endpoint {old_endpoint.id}: {e}')
                        )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} endpoints')
        
        self.stdout.write(
            self.style.SUCCESS(f'Endpoints migrados: {total}')
        )

    def migrate_matches(self, dry_run, batch_size):
        """Migrar partidos"""
        self.stdout.write('Migrando partidos...')
        
        # Usar MatchAllManager para incluir TODOS los partidos, incluyendo withdrawn
        old_matches = OldMatch.all_objects.prefetch_related('league', 'home_team', 'away_team').all()
        total = old_matches.count()
        
        if total == 0:
            self.stdout.write('No hay partidos para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} partidos (incluyendo withdrawn)')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_matches[i:i + batch_size]
                for old_match in batch:
                    # Obtener nueva liga
                    try:
                        new_league = NewLeague.objects.get(id=old_match.league.id)
                    except NewLeague.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Liga no encontrada: {old_match.league.id}')
                        )
                        continue
                    
                    # Obtener nuevos equipos (temporales hasta que se cree teams app)
                    new_home_team = None
                    new_away_team = None
                    
                    if old_match.home_team:
                        try:
                            # Usar el modelo Team original (videos.Team) para foreign keys temporales
                            from videosvoley.videos.models import Team
                            new_home_team = Team.objects.get(id=old_match.home_team.id)
                        except Team.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Equipo local no encontrado: {old_match.home_team.id}')
                            )
                    
                    if old_match.away_team:
                        try:
                            # Usar el modelo Team original (videos.Team) para foreign keys temporales
                            from videosvoley.videos.models import Team
                            new_away_team = Team.objects.get(id=old_match.away_team.id)
                        except Team.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Equipo visitante no encontrado: {old_match.away_team.id}')
                            )
                    
                    NewMatch.objects.update_or_create(
                        id=old_match.id,  # Mantener mismo ID
                        defaults={
                            'league': new_league,
                            'home_team': new_home_team,
                            'away_team': new_away_team,
                            'home_team_text': old_match.home_team_text,
                            'away_team_text': old_match.away_team_text,
                            'is_friendly': old_match.is_friendly,
                            'match_date': old_match.match_date,
                            'venue': old_match.venue,
                            'city': old_match.city,
                            'round_number': old_match.round_number,
                            'home_score': old_match.home_score,
                            'away_score': old_match.away_score,
                            'status': old_match.status,
                            'federation_id': old_match.federation_id,
                            'referee1': old_match.referee1,
                            'referee2': old_match.referee2,
                            'scorer': old_match.scorer,
                            'timekeeper': old_match.timekeeper,
                            'delegate': old_match.delegate,
                            'field_address': old_match.field_address,
                            'federation_club_local_id': old_match.federation_club_local_id,
                            'federation_club_away_id': old_match.federation_club_away_id,
                            'acta_html': old_match.acta_html,
                            'created_at': old_match.created_at,
                            'updated_at': old_match.updated_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} partidos')
        
        self.stdout.write(
            self.style.SUCCESS(f'Partidos migrados: {total}')
        )

    def migrate_standings(self, dry_run, batch_size):
        """Migrar clasificaciones"""
        self.stdout.write('Migrando clasificaciones...')
        
        old_standings = OldStanding.objects.select_related('league', 'team').all()
        total = old_standings.count()
        
        if total == 0:
            self.stdout.write('No hay clasificaciones para migrar')
            return
        
        self.stdout.write(f'Encontradas {total} clasificaciones')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_standings[i:i + batch_size]
                for old_standing in batch:
                    # Obtener nueva liga
                    try:
                        new_league = NewLeague.objects.get(id=old_standing.league.id)
                    except NewLeague.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Liga no encontrada: {old_standing.league.id}')
                        )
                        continue
                    
                    # Obtener nuevo equipo (temporal hasta que se cree teams app)
                    new_team = None
                    if old_standing.team:
                        try:
                            # Usar el modelo Team original (videos.Team) para foreign keys temporales
                            from videosvoley.videos.models import Team
                            new_team = Team.objects.get(id=old_standing.team.id)
                        except Team.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Equipo no encontrado: {old_standing.team.id}')
                            )
                            continue
                    
                    NewStanding.objects.update_or_create(
                        league=new_league,
                        team=new_team,
                        defaults={
                            'league': new_league,
                            'team': new_team,
                            'position': old_standing.position,
                            'played': old_standing.played,
                            'won': old_standing.won,
                            'lost': old_standing.lost,
                            'sets_for': old_standing.sets_for,
                            'sets_against': old_standing.sets_against,
                            'points_for': old_standing.points_for,
                            'points_against': old_standing.points_against,
                            'total_points': old_standing.total_points,
                            'wins_3_0': old_standing.wins_3_0,
                            'wins_3_1': old_standing.wins_3_1,
                            'wins_3_2': old_standing.wins_3_2,
                            'losses_2_3': old_standing.losses_2_3,
                            'losses_1_3': old_standing.losses_1_3,
                            'losses_0_3': old_standing.losses_0_3,
                            'updated_at': old_standing.updated_at,
                        }
                    )
                self.stdout.write(f'Procesadas {min(i + batch_size, total)} clasificaciones')
        
        self.stdout.write(
            self.style.SUCCESS(f'Clasificaciones migradas: {total}')
        )