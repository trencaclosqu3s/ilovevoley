from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Category, Video, Comment, Image


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'match_link', 'created_by', 'created_at']
    list_filter = ['category', 'created_at', 'created_by']
    search_fields = ['title', 'description', 'youtube_url']
    readonly_fields = ['created_at', 'embed_preview']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('title', 'youtube_url', 'description', 'category')
        }),
        ('Partido', {
            'fields': ('match',),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
        ('Vista Previa', {
            'fields': ('embed_preview',),
            'classes': ('collapse',)
        }),
    )
    
    def match_link(self, obj):
        if obj.match:
            url = reverse('admin:competitions_match_change', args=[obj.match.id])
            return format_html('<a href="{}">{}</a>', url, obj.match)
        return '-'
    match_link.short_description = 'Partido'
    
    def embed_preview(self, obj):
        if obj.youtube_url:
            embed_url = obj.get_embed_url()
            return format_html(
                '<iframe width="560" height="315" src="{}" frameborder="0" allowfullscreen></iframe>',
                embed_url
            )
        return 'No hay URL de YouTube'
    embed_preview.short_description = 'Vista Previa'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'video', 'content_preview', 'created_at']
    list_filter = ['created_at', 'video__category']
    search_fields = ['user__username', 'content', 'video__title']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Contenido'


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'image_preview', 'image_type', 'status', 'match_link', 'uploaded_by', 'upload_date']
    list_filter = ['status', 'image_type', 'year', 'upload_date', 'uploaded_by']
    search_fields = ['title', 'description', 'tags']
    readonly_fields = ['upload_date', 'moderation_date', 'vision_api_details_display']
    ordering = ['-upload_date']
    
    fieldsets = (
        ('Imagen', {
            'fields': ('image', 'title', 'description', 'image_type')
        }),
        ('Etiquetas', {
            'fields': ('tags', 'auto_tags', 'all_tags_display'),
            'classes': ('collapse',)
        }),
        ('Relaciones', {
            'fields': ('match', 'categories', 'year'),
            'classes': ('collapse',)
        }),
        ('Moderación', {
            'fields': ('status', 'moderated_by', 'moderation_date', 'moderation_notes'),
        }),
        ('Google Vision API', {
            'fields': ('vision_api_checked', 'vision_api_safe', 'vision_api_details_display'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('uploaded_by', 'upload_date', 'original_format', 'was_converted'),
            'classes': ('collapse',)
        }),
    )
    
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="100" height="100" style="object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return 'Sin imagen'
    image_preview.short_description = 'Vista Previa'
    
    def match_link(self, obj):
        if obj.match:
            url = reverse('admin:competitions_match_change', args=[obj.match.id])
            return format_html('<a href="{}">{}</a>', url, obj.match)
        return '-'
    match_link.short_description = 'Partido'
    
    def all_tags_display(self, obj):
        return ', '.join(obj.all_tags)
    all_tags_display.short_description = 'Todas las Etiquetas'
    
    def vision_api_details_display(self, obj):
        if obj.vision_api_details:
            return format_html('<pre>{}</pre>', str(obj.vision_api_details))
        return 'Sin detalles'
    vision_api_details_display.short_description = 'Detalles Vision API'
    
    actions = ['approve_images', 'reject_images']
    
    def approve_images(self, request, queryset):
        updated = queryset.update(
            status='approved',
            moderated_by=request.user,
            moderation_date=timezone.now()
        )
        self.message_user(request, f'{updated} imágenes aprobadas.')
    approve_images.short_description = 'Aprobar imágenes seleccionadas'
    
    def reject_images(self, request, queryset):
        updated = queryset.update(
            status='rejected',
            moderated_by=request.user,
            moderation_date=timezone.now()
        )
        self.message_user(request, f'{updated} imágenes rechazadas.')
    reject_images.short_description = 'Rechazar imágenes seleccionadas'