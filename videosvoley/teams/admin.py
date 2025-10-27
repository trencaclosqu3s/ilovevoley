from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Club, Team, ClubManager, TeamManager


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = [
        'official_name', 'federation_id', 'province', 'active_teams_count', 
        'total_teams_count', 'created_at'
    ]
    list_filter = ['province', 'created_at', 'updated_at']
    search_fields = ['official_name', 'federation_id', 'president', 'email']
    readonly_fields = ['created_at', 'updated_at', 'logo_federation_url', 'active_teams_count', 'total_teams_count']
    ordering = ['official_name']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('federation_id', 'official_name', 'president')
        }),
        ('Contacto', {
            'fields': ('email', 'phone', 'address'),
            'classes': ('collapse',)
        }),
        ('Instalaciones', {
            'fields': ('venue_name', 'venue_address', 'province'),
            'classes': ('collapse',)
        }),
        ('Redes Sociales', {
            'fields': ('website', 'instagram', 'facebook', 'twitter'),
            'classes': ('collapse',)
        }),
        ('Logo', {
            'fields': ('logo_url', 'logo_federation_url'),
            'classes': ('collapse',)
        }),
        ('Estadísticas', {
            'fields': ('active_teams_count', 'total_teams_count'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_all_teams', 'deactivate_all_teams']
    
    def activate_all_teams(self, request, queryset):
        for club in queryset:
            club.teams.update(is_active=True)
        self.message_user(request, f'Equipos activados para {queryset.count()} clubs.')
    activate_all_teams.short_description = 'Activar todos los equipos de los clubs seleccionados'
    
    def deactivate_all_teams(self, request, queryset):
        for club in queryset:
            club.teams.update(is_active=False)
        self.message_user(request, f'Equipos desactivados para {queryset.count()} clubs.')
    deactivate_all_teams.short_description = 'Desactivar todos los equipos de los clubs seleccionados'


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'club', 'category', 'is_active', 'is_our_team', 
        'federation_id', 'created_at'
    ]
    list_filter = ['is_active', 'category', 'club', 'created_at']
    search_fields = ['name', 'federation_id', 'sponsor_name', 'club__official_name']
    readonly_fields = ['created_at', 'display_logo', 'full_name', 'is_our_team']
    ordering = ['name']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'club', 'category', 'is_active')
        }),
        ('Patrocinio', {
            'fields': ('sponsor_name', 'full_name'),
            'classes': ('collapse',)
        }),
        ('Logo', {
            'fields': ('logo_url', 'display_logo'),
            'classes': ('collapse',)
        }),
        ('Configuración', {
            'fields': ('is_our_team',),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_teams', 'deactivate_teams', 'mark_as_our_teams']
    
    def activate_teams(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} equipos activados.')
    activate_teams.short_description = 'Activar equipos seleccionados'
    
    def deactivate_teams(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} equipos desactivados.')
    deactivate_teams.short_description = 'Desactivar equipos seleccionados'
    
    def mark_as_our_teams(self, request, queryset):
        # Esta acción requeriría modificar la configuración, por ahora solo informativo
        self.message_user(request, f'Para marcar como nuestros equipos, actualizar CLUB_TEAM_NAMES en settings.')
    mark_as_our_teams.short_description = 'Marcar como nuestros equipos (requiere configuración)'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('club', 'category')


class TeamInline(admin.TabularInline):
    """Inline para mostrar equipos en el admin de clubs"""
    model = Team
    extra = 0
    fields = ['name', 'federation_id', 'category', 'is_active', 'sponsor_name']
    readonly_fields = ['federation_id']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category')


# Agregar inline a ClubAdmin
ClubAdmin.inlines = [TeamInline]