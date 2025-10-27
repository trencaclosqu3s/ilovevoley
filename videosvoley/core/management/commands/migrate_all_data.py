"""
Comando maestro para migrar todos los datos de la app videos a las nuevas apps.
Ejecuta todas las migraciones en el orden correcto con foreign keys temporales.
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command
import time


class Command(BaseCommand):
    help = 'Migra todos los datos de videos a las nuevas apps en el orden correcto'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecutar en modo dry-run (no realizar cambios reales)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Tamaño del lote para procesamiento (default: 100)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.1,
            help='Delay entre lotes en segundos (default: 0.1)',
        )
        parser.add_argument(
            '--skip-backup',
            action='store_true',
            help='Saltar la creación de backup (usar con precaución)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        delay = options['delay']
        skip_backup = options['skip_backup']

        self.stdout.write(
            self.style.SUCCESS('🚀 Iniciando migración completa de datos...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  MODO DRY-RUN: No se realizarán cambios reales')
            )

        # Lista de comandos de migración en orden correcto
        migration_commands = [
            {
                'command': 'migrate_content_data',
                'description': 'Migrar datos de content (Video, Comment, Image, Category)',
                'app': 'content'
            },
            {
                'command': 'migrate_teams_data',
                'description': 'Migrar datos de teams (Team, Club)',
                'app': 'teams'
            },
            {
                'command': 'migrate_competitions_data',
                'description': 'Migrar datos de competitions (League, Match, Standing, ScrapingEndpoint)',
                'app': 'competitions'
            },
            {
                'command': 'migrate_rosters_data',
                'description': 'Migrar datos de rosters (Person, PlayerRole, StaffRole)',
                'app': 'rosters'
            }
        ]

        # Crear backup si no se salta
        if not skip_backup and not dry_run:
            self.stdout.write('💾 Creando backup de la base de datos...')
            try:
                call_command('dbbackup', '--compress')
                self.stdout.write(
                    self.style.SUCCESS('✅ Backup creado exitosamente')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'⚠️  No se pudo crear backup: {e}')
                )
                self.stdout.write('Continuando sin backup...')

        # Ejecutar migraciones en orden
        total_commands = len(migration_commands)
        for i, migration in enumerate(migration_commands, 1):
            self.stdout.write(
                f'\n📦 [{i}/{total_commands}] {migration["description"]}...'
            )
            
            try:
                # Preparar argumentos del comando
                command_args = []
                if dry_run:
                    command_args.append('--dry-run')
                command_args.extend(['--batch-size', str(batch_size)])
                if delay > 0:
                    command_args.extend(['--delay', str(delay)])

                # Ejecutar comando de migración
                call_command(migration['command'], *command_args)
                
                self.stdout.write(
                    self.style.SUCCESS(f'✅ {migration["description"]} completado')
                )
                
                # Delay entre comandos
                if delay > 0 and i < total_commands:
                    time.sleep(delay)
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'❌ Error en {migration["description"]}: {e}')
                )
                self.stdout.write(
                    self.style.ERROR('🛑 Migración interrumpida. Revisar errores antes de continuar.')
                )
                return

        # Resumen final
        self.stdout.write('\n' + '='*60)
        self.stdout.write(
            self.style.SUCCESS('🎉 ¡MIGRACIÓN COMPLETA EXITOSA!')
        )
        self.stdout.write('='*60)
        
        if dry_run:
            self.stdout.write('📋 Resumen de datos que se migrarían:')
        else:
            self.stdout.write('📊 Resumen de datos migrados:')
            
        self.stdout.write('  • Content: Videos, imágenes, comentarios, categorías')
        self.stdout.write('  • Teams: Equipos y clubs')
        self.stdout.write('  • Competitions: Ligas, partidos, clasificaciones, endpoints')
        self.stdout.write('  • Rosters: Personas, roles de jugadores y staff')
        
        if not dry_run:
            self.stdout.write('\n🔗 Próximo paso: Actualizar foreign keys en FASE 2.7')
        else:
            self.stdout.write('\n💡 Para ejecutar la migración real, omitir --dry-run')