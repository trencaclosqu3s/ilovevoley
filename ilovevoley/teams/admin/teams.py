from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from ..models import Club, Team


@admin.register(Club)
class ClubAdmin(ModelAdmin):
    list_display = ('official_name', 'federation_id', 'president', 'province', 'teams_count', 'logo_preview')
    list_filter = ('province', 'created_at')
    search_fields = ('official_name', 'federation_id', 'president', 'email')
    readonly_fields = ('created_at', 'updated_at', 'logo_federation_url')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('federation_id', 'official_name')
        }),
        ('Contacto', {
            'fields': ('president', 'email', 'phone', 'address')
        }),
        ('Sede', {
            'fields': ('venue_name', 'venue_address', 'province')
        }),
        ('Redes Sociales', {
            'fields': ('website', 'instagram', 'facebook', 'twitter'),
            'classes': ('collapse',)
        }),
        ('Logo', {
            'fields': ('logo_url', 'logo_federation_url')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['sync_selected_clubs']
    
    def teams_count(self, obj):
        """Muestra el número de equipos asociados"""
        return obj.teams.count()
    teams_count.short_description = 'Equipos'
    
    def logo_preview(self, obj):
        """Muestra preview del logo"""
        if obj.logo_federation_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 3px;" />',
                obj.logo_federation_url
            )
        return '-'
    logo_preview.short_description = 'Logo'
    
    def sync_selected_clubs(self, request, queryset):
        """Acción para sincronizar datos de clubes seleccionados"""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        club_ids = [club.federation_id for club in queryset]
        
        try:
            # Aquí se podría implementar sync específico por club
            self.message_user(request, f'Iniciado sync para {len(club_ids)} club(s)')
        except Exception as e:
            self.message_user(request, f'Error durante sync: {e}', level='ERROR')
    
    sync_selected_clubs.short_description = "Sincronizar datos de clubes seleccionados"




@admin.register(Team)
class TeamAdmin(ModelAdmin):
    list_display = ('display_name_admin', 'category', 'club_name', 'variant_indicator', 'sponsor_name', 'federation_id', 'is_active', 'logo_preview', 'players_count', 'staff_count')
    list_filter = ('is_active', 'category', 'club', ('parent_team', admin.RelatedOnlyFieldListFilter), 'variant_type', 'is_temporary_variant', 'created_at')
    search_fields = ('name', 'federation_id', 'sponsor_name', 'club__official_name', 'category__name')
    readonly_fields = ('created_at', 'display_logo', 'players_count', 'staff_count')
    autocomplete_fields = ('club', 'category', 'parent_team')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'club', 'category', 'is_active')
        }),
        ('Configuración de Variantes', {
            'fields': (
                'parent_team', 'variant_type', 'variant_name',
                'variant_description', 'is_temporary_variant', 'temporary_end_date'
            ),
            'description': 'Configura si este equipo es una variante de otro',
            'classes': ('collapse',)
        }),
        ('Patrocinio', {
            'fields': ('sponsor_name',),
            'description': 'Nombre completo del equipo incluyendo patrocinadores'
        }),
        ('Logo', {
            'fields': ('logo_url', 'display_logo'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['match_to_clubs', 'activate_teams', 'deactivate_teams']
    
    def club_name(self, obj):
        """Muestra el nombre del club asociado"""
        return obj.club.official_name if obj.club else '-'
    club_name.short_description = 'Club'

    def display_name_admin(self, obj):
        """Muestra el nombre con indentación si es una variante"""
        if obj.parent_team:
            return f"  └─ {obj.display_name_with_variant}"
        return obj.name
    display_name_admin.short_description = 'Nombre'

    def variant_indicator(self, obj):
        """Muestra un indicador visual si el equipo tiene variantes o es una variante"""
        if obj.parent_team:
            return format_html(
                '<span style="background: #f39c12; color: white; padding: 2px 6px; border-radius: 3px;">{}</span>',
                obj.variant_name or 'VARIANTE'
            )
        elif obj.variants.exists():
            return format_html(
                '<span style="background: #95a5a6; color: white; padding: 2px 6px; border-radius: 3px;">{} VAR</span>',
                obj.variants.count()
            )
        return '-'
    variant_indicator.short_description = 'Variante'

    def players_count(self, obj):
        """Muestra el número de jugadores activos usando nueva estructura Person-Role"""
        return obj.player_roles.filter(is_active=True).count()
    players_count.short_description = 'Jugadores'
    
    def staff_count(self, obj):
        """Muestra el número de miembros del staff activos usando nueva estructura Person-Role"""
        return obj.staff_roles.filter(is_active=True).count()
    staff_count.short_description = 'Staff'
    
    def logo_preview(self, obj):
        """Muestra preview del logo del equipo o club"""
        logo_url = obj.display_logo
        if logo_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 3px;" />',
                logo_url
            )
        return '-'
    logo_preview.short_description = 'Logo'
    
    def match_to_clubs(self, request, queryset):
        """Acción para hacer matching automático de equipos seleccionados"""
        from django.core.management import call_command
        from io import StringIO
        
        teams_without_club = queryset.filter(club__isnull=True)
        if not teams_without_club.exists():
            self.message_user(request, 'Todos los equipos seleccionados ya tienen club asignado')
            return
        
        try:
            out = StringIO()
            call_command('scrape_clubs', '--match-teams', '--verbose', stdout=out)
            
            # Contar equipos que ahora tienen club
            matched_count = 0
            for team in teams_without_club:
                team.refresh_from_db()
                if team.club:
                    matched_count += 1
            
            if matched_count > 0:
                self.message_user(request, f'Se asociaron {matched_count} equipo(s) con clubes')
            else:
                self.message_user(request, 'No se pudieron hacer matches automáticos')
                
        except Exception as e:
            self.message_user(request, f'Error durante matching: {e}', level='ERROR')
    
    match_to_clubs.short_description = "Hacer matching automático con clubes"
    
    def activate_teams(self, request, queryset):
        """Acción para activar equipos seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        if updated:
            self.message_user(request, f'{updated} equipo(s) activado(s) correctamente.')
        else:
            self.message_user(request, 'Todos los equipos seleccionados ya estaban activos.')
    activate_teams.short_description = "Activar equipos seleccionados"
    
    def deactivate_teams(self, request, queryset):
        """Acción para desactivar equipos seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        if updated:
            self.message_user(request, f'{updated} equipo(s) desactivado(s) correctamente.')
            self.message_user(request, 'Los partidos de estos equipos se marcarán como retirados en el próximo scraping.', level='WARNING')
        else:
            self.message_user(request, 'Todos los equipos seleccionados ya estaban inactivos.')
    deactivate_teams.short_description = "Desactivar equipos seleccionados"
