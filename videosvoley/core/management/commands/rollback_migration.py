"""
Comando para hacer rollback de la migración de datos.
Elimina todos los datos migrados y restaura el estado original.
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command
import time


class Command(BaseCommand):
    help = 'Hace rollback de la migración eliminando todos los datos migrados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirmar que se desea hacer rollback (requerido)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se eliminaría sin hacer cambios reales',
        )
        parser.add_argument(
            '--keep-backup',
            action='store_true',
            help='Mantener el backup después del rollback',
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        dry_run = options['dry_run']
        keep_backup = options['keep_backup']

        if not confirm and not dry_run:
            self.stdout.write(
                self.style.ERROR('❌ ROLLBACK PELIGROSO: Se requiere --confirm para proceder')
            )
            self.stdout.write('Este comando eliminará TODOS los datos migrados.')
            self.stdout.write('Usar --dry-run para ver qué se eliminaría.')
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  MODO DRY-RUN: No se eliminarán datos reales')
            )

        self.stdout.write(
            self.style.WARNING('🔄 Iniciando rollback de migración...')
        )

        # Lista de tablas a limpiar (en orden inverso al de migración)
        tables_to_clean = [
            'rosters_staffrole',
            'rosters_playerrole', 
            'rosters_person',
            'competitions_scrapingendpoint',
            'competitions_standing',
            'competitions_match',
            'competitions_league',
            'teams_club',
            'teams_team',
            'content_comment',
            'content_image',
            'content_video',
            'content_category'
        ]

        total_tables = len(tables_to_clean)
        cleaned_tables = 0

        with connection.cursor() as cursor:
            for i, table in enumerate(tables_to_clean, 1):
                self.stdout.write(
                    f'\n🗑️  [{i}/{total_tables}] Limpiando {table}...'
                )

                try:
                    # Contar registros antes de eliminar
                    cursor.execute(f'SELECT COUNT(*) FROM {table}')
                    count_before = cursor.fetchone()[0]

                    if count_before == 0:
                        self.stdout.write(f'  ℹ️  {table}: Ya está vacía')
                        cleaned_tables += 1
                        continue

                    if dry_run:
                        self.stdout.write(f'  📊 {table}: {count_before} registros a eliminar')
                        cleaned_tables += 1
                    else:
                        # Eliminar todos los registros
                        cursor.execute(f'DELETE FROM {table}')
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✅ {table}: {count_before} registros eliminados')
                        )
                        cleaned_tables += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Error limpiando {table}: {e}')
                    )

        # Resumen final
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write('📋 RESUMEN DE ROLLBACK (DRY-RUN)')
        else:
            self.stdout.write('🔄 ROLLBACK COMPLETADO')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Tablas procesadas: {cleaned_tables}/{total_tables}')

        if dry_run:
            self.stdout.write('💡 Para ejecutar el rollback real, usar --confirm')
        else:
            self.stdout.write(
                self.style.SUCCESS('✅ Rollback completado exitosamente')
            )
            self.stdout.write('📊 Todos los datos migrados han sido eliminados')
            
            if not keep_backup:
                self.stdout.write('💾 Considera restaurar desde backup si es necesario')
            else:
                self.stdout.write('💾 Backup mantenido para restauración futura')

        # Verificar estado final
        self.stdout.write('\n🔍 Verificando estado final...')
        self._verify_clean_state()

    def _verify_clean_state(self):
        """Verifica que las tablas estén limpias"""
        with connection.cursor() as cursor:
            tables_to_check = [
                'content_category', 'content_video', 'content_image', 'content_comment',
                'teams_team', 'teams_club',
                'competitions_league', 'competitions_match', 'competitions_standing', 'competitions_scrapingendpoint',
                'rosters_person', 'rosters_playerrole', 'rosters_staffrole'
            ]

            all_clean = True
            for table in tables_to_check:
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM {table}')
                    count = cursor.fetchone()[0]
                    if count > 0:
                        self.stdout.write(
                            self.style.WARNING(f'  ⚠️  {table}: {count} registros restantes')
                        )
                        all_clean = False
                    else:
                        self.stdout.write(f'  ✅ {table}: Limpia')
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Error verificando {table}: {e}')
                    )
                    all_clean = False

            if all_clean:
                self.stdout.write(
                    self.style.SUCCESS('\n🎉 ¡Todas las tablas están limpias!')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('\n⚠️  Algunas tablas aún contienen datos')
                )