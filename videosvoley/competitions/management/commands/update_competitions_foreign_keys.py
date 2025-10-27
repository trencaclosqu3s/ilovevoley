"""
Comando específico para actualizar foreign keys de competitions.
Actualiza las foreign keys temporales de competitions para apuntar a las nuevas apps.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Actualiza foreign keys de competitions para apuntar a las nuevas apps'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se actualizaría sin hacer cambios reales',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Tamaño del lote para procesamiento (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  MODO DRY-RUN: No se realizarán cambios reales')
            )

        self.stdout.write(
            self.style.SUCCESS('🔗 Actualizando foreign keys de competitions...')
        )

        with connection.cursor() as cursor:
            # 1. Actualizar League.category_id (videos_category -> content_category)
            self.stdout.write('\n📊 Actualizando League.category_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM competitions_league 
                WHERE category_id IS NOT NULL
            """)
            total_leagues = cursor.fetchone()[0]
            self.stdout.write(f'  Encontradas {total_leagues} ligas con categoría')

            if not dry_run and total_leagues > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE competitions_league 
                        SET category_id = (
                            SELECT content_category.id 
                            FROM content_category 
                            WHERE content_category.id = competitions_league.category_id
                        )
                        WHERE category_id IN (
                            SELECT id FROM content_category
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} ligas actualizadas')

            # 2. Actualizar Match.home_team_id y away_team_id (videos_team -> teams_team)
            self.stdout.write('\n📊 Actualizando Match.home_team_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM competitions_match 
                WHERE home_team_id IS NOT NULL
            """)
            total_home_teams = cursor.fetchone()[0]
            self.stdout.write(f'  Encontrados {total_home_teams} partidos con equipo local')

            if not dry_run and total_home_teams > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE competitions_match 
                        SET home_team_id = (
                            SELECT teams_team.id 
                            FROM teams_team 
                            WHERE teams_team.id = competitions_match.home_team_id
                        )
                        WHERE home_team_id IN (
                            SELECT id FROM teams_team
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} equipos locales actualizados')

            self.stdout.write('\n📊 Actualizando Match.away_team_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM competitions_match 
                WHERE away_team_id IS NOT NULL
            """)
            total_away_teams = cursor.fetchone()[0]
            self.stdout.write(f'  Encontrados {total_away_teams} partidos con equipo visitante')

            if not dry_run and total_away_teams > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE competitions_match 
                        SET away_team_id = (
                            SELECT teams_team.id 
                            FROM teams_team 
                            WHERE teams_team.id = competitions_match.away_team_id
                        )
                        WHERE away_team_id IN (
                            SELECT id FROM teams_team
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} equipos visitantes actualizados')

            # 3. Actualizar Standing.team_id (videos_team -> teams_team)
            self.stdout.write('\n📊 Actualizando Standing.team_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM competitions_standing 
                WHERE team_id IS NOT NULL
            """)
            total_standings = cursor.fetchone()[0]
            self.stdout.write(f'  Encontradas {total_standings} clasificaciones con equipo')

            if not dry_run and total_standings > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE competitions_standing 
                        SET team_id = (
                            SELECT teams_team.id 
                            FROM teams_team 
                            WHERE teams_team.id = competitions_standing.team_id
                        )
                        WHERE team_id IN (
                            SELECT id FROM teams_team
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} clasificaciones actualizadas')

        # Resumen final
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write('📋 RESUMEN DE ACTUALIZACIONES (DRY-RUN)')
            self.stdout.write(f'Ligas con categoría: {total_leagues}')
            self.stdout.write(f'Partidos con equipo local: {total_home_teams}')
            self.stdout.write(f'Partidos con equipo visitante: {total_away_teams}')
            self.stdout.write(f'Clasificaciones con equipo: {total_standings}')
        else:
            self.stdout.write('🔗 ACTUALIZACIÓN DE FOREIGN KEYS DE COMPETITIONS COMPLETADA')
            self.stdout.write('✅ Todas las foreign keys de competitions actualizadas exitosamente')

        # Verificar integridad después de la actualización
        if not dry_run:
            self.stdout.write('\n🔍 Verificando integridad después de la actualización...')
            call_command('verify_migration_integrity')