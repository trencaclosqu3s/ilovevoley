"""
Admin interface para la app content.
Migrado desde videos.admin para la nueva app content.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.conf import settings
from .models import Video, Comment, Category, Image


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'leagues_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)
    
    def leagues_count(self, obj):
        """Muestra el número de ligas asociadas"""
        return obj.leagues.count()
    leagues_count.short_description = 'Ligas'
    
    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'match', 'created_by', 'created_at')
    list_filter = ('category', 'match__league', 'created_at')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('created_at',)
    # autocomplete_fields = ('match',)  # Comentado temporalmente - problema de orden de carga de apps


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['video', 'user', 'content_preview', 'created_at']
    list_filter = ['created_at', 'video__category']
    search_fields = ['content', 'user__username', 'video__title']
    readonly_fields = ['created_at']
    raw_id_fields = ['video', 'user']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Contenido'


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('thumbnail_preview', 'title', 'match', 'categories_display_admin', 'status', 'uploaded_by', 'upload_date', 'moderated_by', 'original_format', 'was_converted')
    list_filter = ('status', 'categories', 'year', 'upload_date', 'match__league', 'was_converted', 'original_format')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('upload_date', 'thumbnail_preview', 'vision_api_details', 'moderation_date', 'original_format', 'was_converted')
    date_hierarchy = 'upload_date'
    actions = ['approve_images', 'reject_images', 'check_with_vision_api']
    filter_horizontal = ('categories',)
    
    fieldsets = (
        ('Imagen', {
            'fields': ('thumbnail_preview', 'image', 'title', 'description', 'image_type', 'tags', 'original_format', 'was_converted')
        }),
        ('Asociación', {
            'fields': ('match', 'categories', 'year'),
            'description': 'Categorías y año se asignan automáticamente desde el partido, pero puedes modificarlas'
        }),
        ('Moderación', {
            'fields': ('status', 'moderated_by', 'moderation_date', 'moderation_notes')
        }),
        ('Google Vision API', {
            'fields': ('vision_api_checked', 'vision_api_safe', 'vision_api_details'),
            'classes': ('collapse',),
            'description': 'Información de verificación automática de contenido'
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'upload_date'),
            'classes': ('collapse',)
        })
    )
    
    def thumbnail_preview(self, obj):
        """Muestra miniatura de la imagen"""
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="80" style="object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return '-'
    thumbnail_preview.short_description = 'Preview'
    
    def categories_display_admin(self, obj):
        """Muestra las categorías de forma legible"""
        cats = obj.categories.all()
        if cats:
            return ', '.join([cat.name for cat in cats])
        return '-'
    categories_display_admin.short_description = 'Categorías'
    
    def get_queryset(self, request):
        """Optimizar consultas con select_related y prefetch_related"""
        return super().get_queryset(request).select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories')
    
    def approve_images(self, request, queryset):
        """Acción masiva para aprobar imágenes"""
        updated = queryset.filter(status='pending').update(
            status='approved',
            moderated_by=request.user,
            moderation_date=timezone.now(),
            moderation_notes='Aprobada masivamente desde admin'
        )
        
        if updated:
            self.message_user(request, f'{updated} imagen(es) aprobada(s) correctamente.')
        else:
            self.message_user(request, 'No hay imágenes pendientes para aprobar.')
    
    approve_images.short_description = "Aprobar imágenes seleccionadas"
    
    def reject_images(self, request, queryset):
        """Acción masiva para rechazar imágenes"""
        updated = queryset.filter(status='pending').update(
            status='rejected',
            moderated_by=request.user,
            moderation_date=timezone.now(),
            moderation_notes='Rechazada masivamente desde admin'
        )
        
        if updated:
            self.message_user(request, f'{updated} imagen(es) rechazada(s) correctamente.')
        else:
            self.message_user(request, 'No hay imágenes pendientes para rechazar.')
    
    reject_images.short_description = "Rechazar imágenes seleccionadas"
    
    def check_with_vision_api(self, request, queryset):
        """Acción para verificar imágenes con Google Vision API"""
        if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
            self.message_user(request, 'Google Vision API no está habilitada.', level='WARNING')
            return
        
        try:
            from .utils import check_image_with_vision_api
            checked_count = 0
            unsafe_count = 0
            
            for image in queryset:
                if not image.vision_api_checked:
                    try:
                        result = check_image_with_vision_api(image.image)
                        image.vision_api_checked = True
                        image.vision_api_safe = result.get('safe', True)
                        image.vision_api_details = result
                        
                        if not result.get('safe', True):
                            unsafe_count += 1
                            # Auto-rechazar si no es segura
                            image.status = 'rejected'
                            image.moderated_by = request.user
                            image.moderation_date = timezone.now()
                            image.moderation_notes = 'Auto-rechazada por Google Vision API'
                        
                        image.save()
                        checked_count += 1
                        
                    except Exception as e:
                        self.message_user(request, f'Error verificando {image.title}: {e}', level='ERROR')
            
            if checked_count > 0:
                self.message_user(request, f'{checked_count} imagen(es) verificada(s) con Vision API.')
                if unsafe_count > 0:
                    self.message_user(request, f'{unsafe_count} imagen(es) marcada(s) como insegura(s).', level='WARNING')
            
        except ImportError:
            self.message_user(request, 'Utilidad de Vision API no disponible.', level='ERROR')
    
    check_with_vision_api.short_description = "Verificar con Google Vision API"
    
    def save_model(self, request, obj, form, change):
        """Auto-asignar moderador en cambios de estado"""
        if change and 'status' in form.changed_data:
            if obj.status in ['approved', 'rejected'] and not obj.moderated_by:
                obj.moderated_by = request.user
                obj.moderation_date = timezone.now()
        
        super().save_model(request, obj, form, change)