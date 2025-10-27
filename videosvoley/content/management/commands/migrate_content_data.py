from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from videosvoley.videos.models import Video as OldVideo, Comment as OldComment, Image as OldImage, Category as OldCategory
from videosvoley.content.models import Video as NewVideo, Comment as NewComment, Image as NewImage, Category as NewCategory


class Command(BaseCommand):
    help = 'Migra datos de content desde la app videos a la nueva app content'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular migración sin hacer cambios reales',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Tamaño del lote para procesar (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        self.stdout.write(
            self.style.SUCCESS('Iniciando migración de datos de content...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se realizarán cambios reales')
            )
        
        try:
            with transaction.atomic():
                # Migrar categorías
                self.migrate_categories(dry_run, batch_size)
                
                # Migrar videos
                self.migrate_videos(dry_run, batch_size)
                
                # Migrar comentarios
                self.migrate_comments(dry_run, batch_size)
                
                # Migrar imágenes
                self.migrate_images(dry_run, batch_size)
                
                if dry_run:
                    # En dry-run, hacer rollback
                    raise Exception("Dry run - rollback")
                
                self.stdout.write(
                    self.style.SUCCESS('Migración completada exitosamente!')
                )
                
        except Exception as e:
            if not dry_run:
                self.stdout.write(
                    self.style.ERROR(f'Error durante la migración: {e}')
                )
                raise
            else:
                self.stdout.write(
                    self.style.SUCCESS('Dry run completado - no se realizaron cambios')
                )

    def migrate_categories(self, dry_run, batch_size):
        """Migrar categorías"""
        self.stdout.write('Migrando categorías...')
        
        old_categories = OldCategory.objects.all()
        total = old_categories.count()
        
        if total == 0:
            self.stdout.write('No hay categorías para migrar')
            return
        
        self.stdout.write(f'Encontradas {total} categorías')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_categories[i:i + batch_size]
                for old_cat in batch:
                    NewCategory.objects.get_or_create(
                        name=old_cat.name,
                        defaults={
                            'description': old_cat.description,
                            'is_active': old_cat.is_active,
                            'created_at': old_cat.created_at,
                        }
                    )
                self.stdout.write(f'Procesadas {min(i + batch_size, total)} categorías')
        
        self.stdout.write(
            self.style.SUCCESS(f'Categorías migradas: {total}')
        )

    def migrate_videos(self, dry_run, batch_size):
        """Migrar videos"""
        self.stdout.write('Migrando videos...')
        
        old_videos = OldVideo.objects.select_related('category', 'created_by').all()
        total = old_videos.count()
        
        if total == 0:
            self.stdout.write('No hay videos para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} videos')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_videos[i:i + batch_size]
                for old_video in batch:
                    # Obtener nueva categoría
                    new_category = None
                    if old_video.category:
                        try:
                            new_category = NewCategory.objects.get(name=old_video.category.name)
                        except NewCategory.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Categoría no encontrada: {old_video.category.name}')
                            )
                    
                    NewVideo.objects.get_or_create(
                        id=old_video.id,  # Mantener mismo ID
                        defaults={
                            'title': old_video.title,
                            'youtube_url': old_video.youtube_url,
                            'description': old_video.description,
                            'category': new_category,
                            'match': old_video.match,  # Foreign key temporal
                            'created_by': old_video.created_by,
                            'created_at': old_video.created_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} videos')
        
        self.stdout.write(
            self.style.SUCCESS(f'Videos migrados: {total}')
        )

    def migrate_comments(self, dry_run, batch_size):
        """Migrar comentarios"""
        self.stdout.write('Migrando comentarios...')
        
        old_comments = OldComment.objects.select_related('video', 'user').all()
        total = old_comments.count()
        
        if total == 0:
            self.stdout.write('No hay comentarios para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} comentarios')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_comments[i:i + batch_size]
                for old_comment in batch:
                    # Obtener nuevo video
                    try:
                        new_video = NewVideo.objects.get(id=old_comment.video.id)
                    except NewVideo.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Video no encontrado: {old_comment.video.id}')
                        )
                        continue
                    
                    NewComment.objects.get_or_create(
                        id=old_comment.id,  # Mantener mismo ID
                        defaults={
                            'video': new_video,
                            'user': old_comment.user,
                            'content': old_comment.content,
                            'created_at': old_comment.created_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} comentarios')
        
        self.stdout.write(
            self.style.SUCCESS(f'Comentarios migrados: {total}')
        )

    def migrate_images(self, dry_run, batch_size):
        """Migrar imágenes"""
        self.stdout.write('Migrando imágenes...')
        
        old_images = OldImage.objects.select_related('uploaded_by', 'match').prefetch_related('categories').all()
        total = old_images.count()
        
        if total == 0:
            self.stdout.write('No hay imágenes para migrar')
            return
        
        self.stdout.write(f'Encontradas {total} imágenes')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_images[i:i + batch_size]
                for old_image in batch:
                    # Obtener nuevas categorías
                    new_categories = []
                    for old_cat in old_image.categories.all():
                        try:
                            new_cat = NewCategory.objects.get(name=old_cat.name)
                            new_categories.append(new_cat)
                        except NewCategory.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Categoría no encontrada: {old_cat.name}')
                            )
                    
                    new_image = NewImage.objects.create(
                        id=old_image.id,  # Mantener mismo ID
                        image=old_image.image,
                        title=old_image.title,
                        description=old_image.description,
                        original_format=old_image.original_format,
                        was_converted=old_image.was_converted,
                        image_type=old_image.image_type,
                        tags=old_image.tags,
                        auto_tags=old_image.auto_tags,
                        match=old_image.match,  # Foreign key temporal
                        year=old_image.year,
                        uploaded_by=old_image.uploaded_by,
                        upload_date=old_image.upload_date,
                        status=old_image.status,
                        moderated_by=old_image.moderated_by,
                        moderation_date=old_image.moderation_date,
                        moderation_notes=old_image.moderation_notes,
                        vision_api_checked=old_image.vision_api_checked,
                        vision_api_safe=old_image.vision_api_safe,
                        vision_api_details=old_image.vision_api_details,
                    )
                    
                    # Asignar categorías
                    for new_cat in new_categories:
                        new_image.categories.add(new_cat)
                
                self.stdout.write(f'Procesadas {min(i + batch_size, total)} imágenes')
        
        self.stdout.write(
            self.style.SUCCESS(f'Imágenes migradas: {total}')
        )