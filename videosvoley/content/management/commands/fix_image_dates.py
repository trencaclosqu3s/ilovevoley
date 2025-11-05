"""
Comando para corregir las fechas de subida de las imágenes migradas
"""
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from videosvoley.content.models import Image as ContentImage


class Command(BaseCommand):
    help = 'Corrige las fechas de subida de las imágenes desde videos_image'

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
        
        # Obtener fechas de subida originales de la tabla videos_image
        cursor.execute("""
            SELECT id, upload_date 
            FROM videos_image 
            ORDER BY id
        """)
        
        original_dates = cursor.fetchall()
        
        if not original_dates:
            self.stdout.write(self.style.WARNING('No se encontraron fechas en videos_image'))
            return
        
        self.stdout.write(f'Encontradas {len(original_dates)} imágenes con fechas originales')
        
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for old_id, upload_date in original_dates:
                try:
                    # Buscar la imagen correspondiente en content_image
                    content_image = ContentImage.objects.filter(id=old_id).first()
                    
                    if not content_image:
                        # No es un error, simplemente no se migró esta imagen
                        continue
                    
                    if dry_run:
                        self.stdout.write(
                            f'[DRY RUN] Actualizaría fecha de "{content_image.title}" '
                            f'de {content_image.upload_date} a {upload_date}'
                        )
                    else:
                        # Actualizar la fecha de subida
                        old_date = content_image.upload_date
                        content_image.upload_date = upload_date
                        content_image.save(update_fields=['upload_date'])
                        
                        self.stdout.write(
                            f'✓ "{content_image.title}": {old_date} → {upload_date}'
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
                self.style.SUCCESS(f'[DRY RUN] Se actualizarían {updated_count} fechas')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Fechas corregidas: {updated_count} imágenes actualizadas')
            )
        
        if errors:
            self.stdout.write(self.style.WARNING(f'⚠️ {len(errors)} errores encontrados:'))
            for error in errors[:5]:  # Mostrar máximo 5 errores
                self.stdout.write(f'  - {error}')
            if len(errors) > 5:
                self.stdout.write(f'  ... y {len(errors) - 5} errores más')
        
        # Verificar resultado
        if not dry_run:
            # Mostrar rango de fechas resultante
            cursor.execute("""
                SELECT MIN(upload_date), MAX(upload_date) 
                FROM content_image
            """)
            min_date, max_date = cursor.fetchone()
            self.stdout.write(f'📊 Rango de fechas después de la corrección: {min_date} a {max_date}')