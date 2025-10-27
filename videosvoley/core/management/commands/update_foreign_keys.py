"""
Comando para actualizar todas las foreign keys temporales para apuntar a las nuevas apps.
Esta es la fase final de migración de datos.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Actualiza todas las foreign keys temporales para apuntar a las nuevas apps'

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
        parser.add_argument(
            '--app',
            choices=['content', 'competitions', 'rosters', 'all'],
            default='all',
            help='App específica a actualizar (default: all)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        app_filter = options['app']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  MODO DRY-RUN: No se realizarán cambios reales')
            )

        self.stdout.write(
            self.style.SUCCESS('🔗 Iniciando actualización de foreign keys...')
        )

        # Definir actualizaciones por app
        updates = {
            'content': [
                {
                    'table': 'content_video',
                    'field': 'category_id',
                    'description': 'Videos -> Category (content)',
                    'old_table': 'videos_category',
                    'new_table': 'content_category'
                },
                {
                    'table': 'content_video',
                    'field': 'match_id',
                    'description': 'Videos -> Match (competitions)',
                    'old_table': 'videos_match',
                    'new_table': 'competitions_match'
                },
                {
                    'table': 'content_image',
                    'field': 'match_id',
                    'description': 'Images -> Match (competitions)',
                    'old_table': 'videos_match',
                    'new_table': 'competitions_match'
                },
                {
                    'table': 'content_comment',
                    'field': 'video_id',
                    'description': 'Comments -> Video (content)',
                    'old_table': 'videos_video',
                    'new_table': 'content_video'
                }
            ],
            'competitions': [
                {
                    'table': 'competitions_league',
                    'field': 'category_id',
                    'description': 'League -> Category (content)',
                    'old_table': 'videos_category',
                    'new_table': 'content_category'
                },
                {
                    'table': 'competitions_match',
                    'field': 'home_team_id',
                    'description': 'Match -> Home Team (teams)',
                    'old_table': 'videos_team',
                    'new_table': 'teams_team'
                },
                {
                    'table': 'competitions_match',
                    'field': 'away_team_id',
                    'description': 'Match -> Away Team (teams)',
                    'old_table': 'videos_team',
                    'new_table': 'teams_team'
                },
                {
                    'table': 'competitions_standing',
                    'field': 'team_id',
                    'description': 'Standing -> Team (teams)',
                    'old_table': 'videos_team',
                    'new_table': 'teams_team'
                }
            ],
            'rosters': [
                {
                    'table': 'rosters_playerrole',
                    'field': 'team_id',
                    'description': 'PlayerRole -> Team (teams)',
                    'old_table': 'videos_team',
                    'new_table': 'teams_team'
                },
                {
                    'table': 'rosters_staffrole',
                    'field': 'team_id',
                    'description': 'StaffRole -> Team (teams)',
                    'old_table': 'videos_team',
                    'new_table': 'teams_team'
                }
            ]
        }

        # Filtrar actualizaciones según app seleccionada
        if app_filter != 'all':
            updates = {app_filter: updates[app_filter]}

        total_updates = 0
        successful_updates = 0

        with connection.cursor() as cursor:
            for app_name, app_updates in updates.items():
                self.stdout.write(f'\n📦 Actualizando {app_name.upper()}...')
                
                for update in app_updates:
                    self.stdout.write(f'  🔄 {update["description"]}...')
                    
                    # Verificar que existen registros para actualizar
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {update['table']} 
                        WHERE {update['field']} IS NOT NULL
                    """)
                    total_records = cursor.fetchone()[0]
                    
                    if total_records == 0:
                        self.stdout.write(f'    ℹ️  No hay registros para actualizar')
                        continue
                    
                    if dry_run:
                        self.stdout.write(f'    📊 {total_records} registros a actualizar')
                        total_updates += total_records
                        continue
                    
                    # Actualizar foreign keys
                    try:
                        with transaction.atomic():
                            # Verificar que los IDs existen en ambas tablas
                            cursor.execute(f"""
                                UPDATE {update['table']} 
                                SET {update['field']} = (
                                    SELECT new_id FROM (
                                        SELECT old.id as old_id, new.id as new_id
                                        FROM {update['old_table']} old
                                        INNER JOIN {update['new_table']} new ON old.id = new.id
                                    ) mapping
                                    WHERE mapping.old_id = {update['table']}.{update['field']}
                                )
                                WHERE {update['field']} IN (
                                    SELECT old.id FROM {update['old_table']} old
                                    INNER JOIN {update['new_table']} new ON old.id = new.id
                                )
                            """)
                            
                            updated_count = cursor.rowcount
                            self.stdout.write(
                                self.style.SUCCESS(f'    ✅ {updated_count} registros actualizados')
                            )
                            total_updates += updated_count
                            successful_updates += updated_count
                            
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'    ❌ Error actualizando: {e}')
                        )

        # Resumen final
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write('📋 RESUMEN DE ACTUALIZACIONES (DRY-RUN)')
            self.stdout.write(f'Total de registros a actualizar: {total_updates}')
        else:
            self.stdout.write('🔗 ACTUALIZACIÓN DE FOREIGN KEYS COMPLETADA')
            self.stdout.write(f'Total de registros actualizados: {successful_updates}')
            
            if successful_updates == total_updates:
                self.stdout.write(
                    self.style.SUCCESS('✅ Todas las foreign keys actualizadas exitosamente')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  {total_updates - successful_updates} registros no se pudieron actualizar')
                )

        # Verificar integridad después de la actualización
        if not dry_run:
            self.stdout.write('\n🔍 Verificando integridad después de la actualización...')
            call_command('verify_migration_integrity')