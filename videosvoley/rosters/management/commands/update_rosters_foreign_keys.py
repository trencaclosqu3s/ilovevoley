"""
Comando específico para actualizar foreign keys de rosters.
Actualiza las foreign keys temporales de rosters para apuntar a las nuevas apps.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Actualiza foreign keys de rosters para apuntar a las nuevas apps'

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
            self.style.SUCCESS('🔗 Actualizando foreign keys de rosters...')
        )

        with connection.cursor() as cursor:
            # 1. Actualizar PlayerRole.team_id (videos_team -> teams_team)
            self.stdout.write('\n📊 Actualizando PlayerRole.team_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM rosters_playerrole 
                WHERE team_id IS NOT NULL
            """)
            total_player_roles = cursor.fetchone()[0]
            self.stdout.write(f'  Encontrados {total_player_roles} roles de jugador con equipo')

            if not dry_run and total_player_roles > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE rosters_playerrole 
                        SET team_id = (
                            SELECT teams_team.id 
                            FROM teams_team 
                            WHERE teams_team.id = rosters_playerrole.team_id
                        )
                        WHERE team_id IN (
                            SELECT id FROM teams_team
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} roles de jugador actualizados')

            # 2. Actualizar StaffRole.team_id (videos_team -> teams_team)
            self.stdout.write('\n📊 Actualizando StaffRole.team_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM rosters_staffrole 
                WHERE team_id IS NOT NULL
            """)
            total_staff_roles = cursor.fetchone()[0]
            self.stdout.write(f'  Encontrados {total_staff_roles} roles de staff con equipo')

            if not dry_run and total_staff_roles > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE rosters_staffrole 
                        SET team_id = (
                            SELECT teams_team.id 
                            FROM teams_team 
                            WHERE teams_team.id = rosters_staffrole.team_id
                        )
                        WHERE team_id IN (
                            SELECT id FROM teams_team
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} roles de staff actualizados')

        # Resumen final
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write('📋 RESUMEN DE ACTUALIZACIONES (DRY-RUN)')
            self.stdout.write(f'Roles de jugador con equipo: {total_player_roles}')
            self.stdout.write(f'Roles de staff con equipo: {total_staff_roles}')
        else:
            self.stdout.write('🔗 ACTUALIZACIÓN DE FOREIGN KEYS DE ROSTERS COMPLETADA')
            self.stdout.write('✅ Todas las foreign keys de rosters actualizadas exitosamente')

        # Verificar integridad después de la actualización
        if not dry_run:
            self.stdout.write('\n🔍 Verificando integridad después de la actualización...')
            call_command('verify_migration_integrity')