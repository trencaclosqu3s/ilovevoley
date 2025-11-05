"""
Comando para migrar datos de álbumes desde videos_image a content_image
"""
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from videosvoley.content.models import Image as ContentImage


class Command(BaseCommand):
    help = 'Migra datos de álbumes desde videos_image a content_image'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin aplicar cambios',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY RUN - No se aplicarán cambios'))
        
        cursor = connection.cursor()
        
        # Obtener imágenes con álbum de la tabla original
        cursor.execute("""
            SELECT id, album_group_id, album_name 
            FROM videos_image 
            WHERE album_group_id IS NOT NULL
        """)
        
        album_images = cursor.fetchall()
        
        if not album_images:
            self.stdout.write(self.style.WARNING('No se encontraron imágenes con álbum'))
            return
        
        self.stdout.write(f'Encontradas {len(album_images)} imágenes con álbum')
        
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for old_id, album_group_id, album_name in album_images:
                try:
                    # Buscar la imagen correspondiente en content_image
                    # Usamos el ID original como referencia
                    content_image = ContentImage.objects.filter(id=old_id).first()
                    
                    if not content_image:
                        errors.append(f'Imagen con ID {old_id} no encontrada en content_image')
                        continue
                    
                    if dry_run:
                        self.stdout.write(
                            f'[DRY RUN] Actualizaría imagen {content_image.title} '
                            f'con álbum {album_group_id} ({album_name})'
                        )
                    else:
                        # Actualizar los campos de álbum
                        content_image.album_group_id = album_group_id
                        content_image.album_name = album_name or ''
                        content_image.save(update_fields=['album_group_id', 'album_name'])
                        
                        self.stdout.write(
                            f'✓ Actualizada imagen "{content_image.title}" '
                            f'con álbum "{album_name}"'
                        )
                    
                    updated_count += 1
                    
                except Exception as e:
                    error_msg = f'Error actualizando imagen ID {old_id}: {str(e)}'
                    errors.append(error_msg)
                    self.stdout.write(self.style.ERROR(error_msg))
        
        # Resumen
        self.stdout.write('')
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(f'[DRY RUN] Se actualizarían {updated_count} imágenes')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Migración completada: {updated_count} imágenes actualizadas')
            )
        
        if errors:
            self.stdout.write(self.style.WARNING(f'⚠️ {len(errors)} errores encontrados:'))
            for error in errors[:5]:  # Mostrar máximo 5 errores
                self.stdout.write(f'  - {error}')
            if len(errors) > 5:
                self.stdout.write(f'  ... y {len(errors) - 5} errores más')
        
        # Verificar resultado
        if not dry_run:
            images_with_albums = ContentImage.objects.exclude(album_group_id__isnull=True).count()
            self.stdout.write(f'📊 Total de imágenes con álbum después de la migración: {images_with_albums}')