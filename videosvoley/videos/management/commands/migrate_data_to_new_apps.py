"""
Comando para migrar datos desde las tablas legacy videos_* a las nuevas apps
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Migra datos desde videos_* a las nuevas apps (content, competitions, teams, rosters)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué se haría sin ejecutar cambios',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN - No se realizarán cambios'))
        
        with transaction.atomic():
            # Migrar Categorías
            self.stdout.write('Migrando categorías...')
            from django.db import connection
            from videosvoley.content.models import Category as ContentCategory
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, description, is_active 
                    FROM videos_category
                """)
                
                categories_map = {}  # Mapear ID viejo → ID nuevo
                
                for old_id, name, description, is_active in cursor.fetchall():
                    if not dry_run:
                        category, created = ContentCategory.objects.get_or_create(
                            name=name,
                            defaults={'description': description or '', 'is_active': is_active}
                        )
                        categories_map[old_id] = category.id
                        if created:
                            self.stdout.write(f'  ✓ Categoría creada: {name}')
                    else:
                        self.stdout.write(f'  → Crearía categoría: {name}')
                        categories_map[old_id] = old_id  # Placeholder
                
                self.stdout.write(f'Categorías migradas: {len(categories_map)}')
                
                # Migrar Videos
                self.stdout.write('\nMigrando videos...')
                from videosvoley.content.models import Video as ContentVideo
                
                cursor.execute("""
                    SELECT id, title, youtube_url, description, created_at, 
                           category_id, match_id, created_by_id
                    FROM videos_video
                """)
                
                videos_count = 0
                for old_id, title, youtube_url, description, created_at, category_id, match_id, created_by_id in cursor.fetchall():
                    if not dry_run:
                        new_category_id = categories_map.get(category_id) if category_id else None
                        
                        video, created = ContentVideo.objects.get_or_create(
                            youtube_url=youtube_url,
                            defaults={
                                'title': title,
                                'description': description or '',
                                'category_id': new_category_id,
                                'match_id': match_id,  # Se actualizará después
                                'created_by_id': created_by_id,
                                'created_at': created_at
                            }
                        )
                        if created:
                            videos_count += 1
                    else:
                        videos_count += 1
                        self.stdout.write(f'  → Migraría video: {title}')
                
                self.stdout.write(f'Videos migrados: {videos_count}')
                
                # Migrar Leagues
                self.stdout.write('\nMigrando ligas...')
                from videosvoley.competitions.models import League as CompetitionLeague
                
                cursor.execute("""
                    SELECT id, name, federation_id, season, competition_type,
                           is_active, category_id
                    FROM videos_league
                """)
                
                leagues_map = {}
                leagues_count = 0
                
                for old_id, name, federation_id, season, competition_type, is_active, category_id in cursor.fetchall():
                    if not dry_run:
                        new_category_id = categories_map.get(category_id) if category_id else None
                        
                        league, created = CompetitionLeague.objects.get_or_create(
                            federation_id=federation_id,
                            defaults={
                                'name': name,
                                'season': season,
                                'competition_type': competition_type,
                                'is_active': is_active,
                                'category_id': new_category_id
                            }
                        )
                        leagues_map[old_id] = league.id
                        if created:
                            leagues_count += 1
                    else:
                        leagues_count += 1
                        leagues_map[old_id] = old_id
                        self.stdout.write(f'  → Migraría liga: {name}')
                
                self.stdout.write(f'Ligas migradas: {leagues_count}')
                
                # Migrar Teams
                self.stdout.write('\nMigrando equipos...')
                from videosvoley.teams.models import Team as TeamTeam
                
                cursor.execute("""
                    SELECT id, name, federation_id, club_id, sponsor_name,
                           logo_url, category_id, is_active
                    FROM videos_team
                """)
                
                teams_map = {}
                teams_count = 0
                
                for old_id, name, federation_id, club_id, sponsor_name, logo_url, category_id, is_active in cursor.fetchall():
                    if not dry_run:
                        new_category_id = categories_map.get(category_id) if category_id else None
                        
                        team, created = TeamTeam.objects.get_or_create(
                            federation_id=federation_id,
                            defaults={
                                'name': name,
                                'club_id': club_id,
                                'sponsor_name': sponsor_name,
                                'logo_url': logo_url,
                                'category_id': new_category_id,
                                'is_active': is_active
                            }
                        )
                        teams_map[old_id] = team.id
                        if created:
                            teams_count += 1
                    else:
                        teams_count += 1
                        teams_map[old_id] = old_id
                        self.stdout.write(f'  → Migraría equipo: {name}')
                
                self.stdout.write(f'Equipos migrados: {teams_count}')
                
                # Migrar Matches
                self.stdout.write('\nMigrando partidos...')
                from videosvoley.competitions.models import Match as CompetitionMatch
                
                cursor.execute("""
                    SELECT id, league_id, home_team_id, away_team_id, match_date,
                           status, home_score, away_score
                    FROM videos_match
                """)
                
                matches_count = 0
                for old_id, league_id, home_team_id, away_team_id, match_date, status, home_score, away_score in cursor.fetchall():
                    if not dry_run:
                        new_league_id = leagues_map.get(league_id)
                        new_home_team_id = teams_map.get(home_team_id)
                        new_away_team_id = teams_map.get(away_team_id)
                        
                        match, created = CompetitionMatch.objects.get_or_create(
                            id=old_id,  # Mantener el mismo ID para compatibilidad
                            defaults={
                                'league_id': new_league_id,
                                'home_team_id': new_home_team_id,
                                'away_team_id': new_away_team_id,
                                'match_date': match_date,
                                'status': status,
                                'home_score': home_score,
                                'away_score': away_score
                            }
                        )
                        if created:
                            matches_count += 1
                    else:
                        matches_count += 1
                        self.stdout.write(f'  → Migraría partido ID: {old_id}')
                
                self.stdout.write(f'Partidos migrados: {matches_count}')
                
        self.stdout.write(self.style.SUCCESS('\nMigración completada'))
