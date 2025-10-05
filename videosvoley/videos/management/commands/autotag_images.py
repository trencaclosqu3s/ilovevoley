"""
Comando para auto-etiquetar imágenes existentes usando Google Vision API
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from videosvoley.videos.models import Image
from videosvoley.videos.utils import check_image_with_vision_api, process_vision_tags_for_volleyball
import time


class Command(BaseCommand):
    help = 'Auto-etiqueta imágenes existentes usando Google Vision API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Número máximo de imágenes a procesar'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Procesar imágenes que ya fueron verificadas con Vision API'
        )
        
        parser.add_argument(
            '--status',
            choices=['pending', 'approved', 'rejected', 'all'],
            default='approved',
            help='Estado de las imágenes a procesar (default: approved)'
        )
        
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay en segundos entre requests a Vision API (default: 1.0)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular ejecución sin hacer cambios'
        )

    def handle(self, *args, **options):
        if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
            raise CommandError('Google Vision API no está habilitada. Configure GOOGLE_VISION_ENABLED=True')

        # Configurar filtros
        queryset = Image.objects.all()
        
        # Filtrar por estado
        if options['status'] != 'all':
            queryset = queryset.filter(status=options['status'])
        
        # Filtrar por si ya fueron procesadas (a menos que se use --force)
        if not options['force']:
            queryset = queryset.filter(vision_api_checked=False)
        
        # Aplicar límite
        if options['limit']:
            queryset = queryset[:options['limit']]
        
        total_images = queryset.count()
        
        if total_images == 0:
            self.stdout.write(
                self.style.WARNING('No se encontraron imágenes para procesar')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(f'Encontradas {total_images} imágenes para procesar')
        )
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Modo DRY-RUN: No se harán cambios'))
        
        processed = 0
        errors = 0
        tags_added = 0
        
        for image in queryset:
            processed += 1
            
            try:
                self.stdout.write(f'[{processed}/{total_images}] Procesando: {image.title}')
                
                if not options['dry_run']:
                    # Procesar imagen con Vision API
                    vision_result = check_image_with_vision_api(
                        image.image, 
                        extract_labels=True, 
                        extract_text=True
                    )
                    
                    # Actualizar información de Vision API
                    image.vision_api_checked = True
                    image.vision_api_safe = vision_result.get('safe', False)
                    image.vision_api_details = vision_result
                    
                    # Procesar etiquetas automáticas
                    detected_labels = vision_result.get('labels', [])
                    detected_text = vision_result.get('text', '')
                    
                    if detected_labels or detected_text:
                        auto_tags = process_vision_tags_for_volleyball(detected_labels, detected_text)
                        if auto_tags:
                            image.add_auto_tags(auto_tags)
                            tags_added += len(auto_tags)
                            self.stdout.write(
                                f'  → Etiquetas añadidas: {", ".join(auto_tags)}'
                            )
                        else:
                            self.stdout.write('  → No se detectaron etiquetas relevantes')
                    else:
                        self.stdout.write('  → No se detectaron etiquetas')
                    
                    # Guardar cambios
                    image.save()
                    
                    # Si la imagen era insegura y está aprobada, advertir
                    if not vision_result.get('safe', True) and image.status == 'approved':
                        self.stdout.write(
                            self.style.WARNING(
                                f'  ⚠️  Imagen marcada como insegura por Vision API: {", ".join(vision_result.get("reasons", []))}'
                            )
                        )
                else:
                    self.stdout.write('  → Simulando procesamiento...')
                
                # Delay para no sobrecargar la API
                if processed < total_images:
                    time.sleep(options['delay'])
                
            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Error procesando imagen {image.id}: {e}')
                )
                continue
        
        # Resumen
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('RESUMEN DE PROCESAMIENTO'))
        self.stdout.write(f'Total de imágenes procesadas: {processed}')
        self.stdout.write(f'Errores: {errors}')
        self.stdout.write(f'Total de etiquetas añadidas: {tags_added}')
        
        if errors > 0:
            self.stdout.write(
                self.style.WARNING(f'Se produjeron {errors} errores durante el procesamiento')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('Procesamiento completado sin errores')
            )