"""
Comando específico para actualizar foreign keys de content.
Actualiza las foreign keys temporales de content para apuntar a las nuevas apps.
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Actualiza foreign keys de content para apuntar a las nuevas apps'

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
            self.style.SUCCESS('🔗 Actualizando foreign keys de content...')
        )

        with connection.cursor() as cursor:
            # 1. Actualizar Video.match_id (videos_match -> competitions_match)
            self.stdout.write('\n📊 Actualizando Video.match_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM content_video 
                WHERE match_id IS NOT NULL
            """)
            total_videos_with_match = cursor.fetchone()[0]
            self.stdout.write(f'  Encontrados {total_videos_with_match} videos con partido')

            if not dry_run and total_videos_with_match > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE content_video 
                        SET match_id = (
                            SELECT competitions_match.id 
                            FROM competitions_match 
                            WHERE competitions_match.id = content_video.match_id
                        )
                        WHERE match_id IN (
                            SELECT id FROM competitions_match
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} videos actualizados')

            # 2. Actualizar Image.match_id (videos_match -> competitions_match)
            self.stdout.write('\n📊 Actualizando Image.match_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM content_image 
                WHERE match_id IS NOT NULL
            """)
            total_images_with_match = cursor.fetchone()[0]
            self.stdout.write(f'  Encontradas {total_images_with_match} imágenes con partido')

            if not dry_run and total_images_with_match > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE content_image 
                        SET match_id = (
                            SELECT competitions_match.id 
                            FROM competitions_match 
                            WHERE competitions_match.id = content_image.match_id
                        )
                        WHERE match_id IN (
                            SELECT id FROM competitions_match
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} imágenes actualizadas')

            # 3. Actualizar Comment.video_id (videos_video -> content_video)
            self.stdout.write('\n📊 Actualizando Comment.video_id...')
            cursor.execute("""
                SELECT COUNT(*) FROM content_comment 
                WHERE video_id IS NOT NULL
            """)
            total_comments = cursor.fetchone()[0]
            self.stdout.write(f'  Encontrados {total_comments} comentarios con video')

            if not dry_run and total_comments > 0:
                with transaction.atomic():
                    cursor.execute("""
                        UPDATE content_comment 
                        SET video_id = (
                            SELECT content_video.id 
                            FROM content_video 
                            WHERE content_video.id = content_comment.video_id
                        )
                        WHERE video_id IN (
                            SELECT id FROM content_video
                        )
                    """)
                    updated = cursor.rowcount
                    self.stdout.write(f'  ✅ {updated} comentarios actualizados')

        # Resumen final
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write('📋 RESUMEN DE ACTUALIZACIONES (DRY-RUN)')
            self.stdout.write(f'Videos con partido: {total_videos_with_match}')
            self.stdout.write(f'Imágenes con partido: {total_images_with_match}')
            self.stdout.write(f'Comentarios con video: {total_comments}')
        else:
            self.stdout.write('🔗 ACTUALIZACIÓN DE FOREIGN KEYS DE CONTENT COMPLETADA')
            self.stdout.write('✅ Todas las foreign keys de content actualizadas exitosamente')

        # Verificar integridad después de la actualización
        if not dry_run:
            self.stdout.write('\n🔍 Verificando integridad después de la actualización...')
            call_command('verify_migration_integrity')