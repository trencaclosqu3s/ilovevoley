from django.contrib import admin
from .models import Document, ChatSession, ChatMessage


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'source_type', 'source_id', 'is_indexed', 'created_at']
    list_filter = ['source_type', 'is_indexed', 'created_at']
    search_fields = ['title', 'content']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['is_indexed']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['user__username', 'title']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['session', 'role', 'content_preview', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['content', 'session__title']
    readonly_fields = ['created_at']
    
    def content_preview(self, obj):
        return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content
    content_preview.short_description = "Vista previa del contenido"