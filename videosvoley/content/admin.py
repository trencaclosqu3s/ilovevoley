"""
Admin interface para la app content.
Migrado desde videos.admin para la nueva app content.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Video, Comment, Category, Image


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'created_by', 'created_at', 'youtube_thumbnail']
    list_filter = ['category', 'created_at', 'created_by']
    search_fields = ['title', 'description', 'created_by__username']
    readonly_fields = ['youtube_url_id', 'created_at', 'updated_at']
    raw_id_fields = ['created_by', 'match']
    
    fieldsets = (
        ('Información básica', {
            'fields': ('title', 'youtube_url', 'youtube_url_id', 'description')
        }),
        ('Clasificación', {
            'fields': ('category', 'match')
        }),
        ('Metadatos', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def youtube_thumbnail(self, obj):
        if obj.youtube_url_id:
            thumbnail_url = f'https://img.youtube.com/vi/{obj.youtube_url_id}/mqdefault.jpg'
            return format_html(
                '<img src="{}" width="120" height="90" style="border-radius: 4px;">',
                thumbnail_url
            )
        return '-'
    youtube_thumbnail.short_description = 'Thumbnail'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Solo para nuevos videos
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


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
    list_display = ['title', 'image_preview', 'image_type', 'status', 'uploaded_by', 'upload_date']
    list_filter = ['status', 'image_type', 'upload_date', 'uploaded_by']
    search_fields = ['title', 'description', 'tags', 'uploaded_by__username']
    readonly_fields = ['upload_date', 'moderation_date', 'vision_api_checked', 'vision_api_safe']
    raw_id_fields = ['uploaded_by', 'moderated_by', 'match']
    
    fieldsets = (
        ('Información básica', {
            'fields': ('image', 'title', 'description', 'image_type')
        }),
        ('Clasificación', {
            'fields': ('categories', 'tags', 'auto_tags', 'match')
        }),
        ('Moderación', {
            'fields': ('status', 'moderated_by', 'moderation_date', 'moderation_notes'),
            'classes': ('collapse',)
        }),
        ('Google Vision API', {
            'fields': ('vision_api_checked', 'vision_api_safe', 'vision_api_details'),
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
                '<img src="{}" width="80" height="80" style="border-radius: 4px; object-fit: cover;">',
                obj.image.url
            )
        return '-'
    image_preview.short_description = 'Imagen'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Solo para nuevas imágenes
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['approve_images', 'reject_images']
    
    def approve_images(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='approved',
            moderated_by=request.user
        )
        self.message_user(request, f'{updated} imágenes aprobadas.')
    approve_images.short_description = 'Aprobar imágenes seleccionadas'
    
    def reject_images(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='rejected',
            moderated_by=request.user
        )
        self.message_user(request, f'{updated} imágenes rechazadas.')
    reject_images.short_description = 'Rechazar imágenes seleccionadas'