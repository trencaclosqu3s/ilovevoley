from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from ..identity import IdentityAssignError, assign_common_identity
from ..models import Club, Team, TeamIdentity, TeamIdentityCandidate


@admin.register(Club)
class ClubAdmin(ModelAdmin):
    list_display = ('official_name', 'federation_id', 'president', 'municipality', 'province', 'teams_count', 'logo_preview')
    list_filter = ('province', 'created_at')
    search_fields = ('official_name', 'federation_id', 'president', 'email')
    readonly_fields = ('created_at', 'updated_at', 'logo_federation_url')
    autocomplete_fields = ('default_venue',)
    
    fieldsets = (
        (_('Información Básica'), {
            'fields': ('federation_id', 'official_name')
        }),
        (_('Contacto'), {
            'fields': ('president', 'email', 'phone', 'address')
        }),
        (_('Sede'), {
            'fields': ('default_venue', 'venue_name', 'venue_address', 'municipality', 'province')
        }),
        (_('Redes Sociales'), {
            'fields': ('website', 'instagram', 'facebook', 'twitter'),
            'classes': ('collapse',)
        }),
        (_('Logo'), {
            'fields': ('logo_url', 'logo_federation_url')
        }),
        (_('Metadata'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['sync_selected_clubs']
    
    def teams_count(self, obj):
        """Muestra el número de equipos asociados"""
        return obj.teams.count()
    teams_count.short_description = _('Equipos')
    
    def logo_preview(self, obj):
        """Muestra preview del logo"""
        if obj.logo_federation_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 3px;" />',
                obj.logo_federation_url
            )
        return '-'
    logo_preview.short_description = _('Logo')
    
    def sync_selected_clubs(self, request, queryset):
        """Acción para sincronizar datos de clubes seleccionados"""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        club_ids = [club.federation_id for club in queryset]
        
        try:
            # Aquí se podría implementar sync específico por club
            self.message_user(request, _('Iniciado sync para %(count)s club(s)') % {'count': len(club_ids)})
        except Exception as e:
            self.message_user(request, _('Error durante sync: %(error)s') % {'error': e}, level='ERROR')
    
    sync_selected_clubs.short_description = _("Sincronizar datos de clubes seleccionados")




@admin.register(TeamIdentity)
class TeamIdentityAdmin(ModelAdmin):
    list_display = (
        'core_name', 'club', 'category', 'gender', 'core_name_normalized',
        'teams_count', 'created_at',
    )
    list_filter = ('category', 'gender', 'club')
    search_fields = ('core_name', 'core_name_normalized', 'club__official_name')
    autocomplete_fields = ('club', 'category')

    @admin.display(description=_('Apariciones'))
    def teams_count(self, obj):
        return obj.teams.count()


@admin.register(TeamIdentityCandidate)
class TeamIdentityCandidateAdmin(ModelAdmin):
    list_display = (
        'new_team', 'suggested_identity', 'suggested_team', 'score', 'reason',
        'status', 'created_at',
    )
    list_filter = ('status',)
    search_fields = ('new_team__name', 'suggested_identity__core_name', 'reason')
    autocomplete_fields = ('new_team', 'suggested_identity', 'suggested_team')
    list_select_related = ('new_team', 'suggested_identity', 'suggested_team')
    actions = ['approve', 'reject']

    @admin.action(description=_('Aprobar vínculo'))
    def approve(self, request, queryset):
        done = []
        for candidate in queryset.filter(status='pending'):
            try:
                done.append(candidate.approve())
            except IdentityAssignError as e:
                self.message_user(request, f'{candidate}: {e}', level='ERROR')
        self.message_user(request, _('%(n)s vínculos aprobados') % {'n': len(done)})

    @admin.action(description=_('Rechazar (identidad nueva)'))
    def reject(self, request, queryset):
        done = [c.reject() for c in queryset.filter(status='pending')]
        self.message_user(request, _('%(n)s candidatas rechazadas') % {'n': len(done)})


@admin.register(Team)
class TeamAdmin(ModelAdmin):
    list_display = ('display_name_admin', 'category', 'gender', 'club_name', 'identity', 'variant_indicator', 'sponsor_name', 'federation_id', 'is_active', 'logo_preview', 'players_count', 'staff_count')
    list_filter = ('is_active', 'category', 'gender', 'club', ('parent_team', admin.RelatedOnlyFieldListFilter), 'variant_type', 'is_temporary_variant', 'created_at')
    search_fields = ('name', 'federation_id', 'sponsor_name', 'club__official_name', 'category__name')
    readonly_fields = ('created_at', 'display_logo', 'players_count', 'staff_count')
    autocomplete_fields = ('club', 'category', 'parent_team', 'identity')
    
    fieldsets = (
        (_('Información Básica'), {
            'fields': ('name', 'federation_id', 'club', 'category', 'gender', 'identity', 'is_active')
        }),
        (_('Configuración de Variantes'), {
            'fields': (
                'parent_team', 'variant_type', 'variant_name',
                'variant_description', 'is_temporary_variant', 'temporary_end_date'
            ),
            'description': _('Configura si este equipo es una variante de otro'),
            'classes': ('collapse',)
        }),
        (_('Patrocinio'), {
            'fields': ('sponsor_name',),
            'description': _('Nombre completo del equipo incluyendo patrocinadores')
        }),
        (_('Logo'), {
            'fields': ('logo_url', 'display_logo'),
            'classes': ('collapse',)
        }),
        (_('Metadata'), {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['match_to_clubs', 'activate_teams', 'deactivate_teams', 'assign_identity']
    
    def club_name(self, obj):
        """Muestra el nombre del club asociado"""
        return obj.club.official_name if obj.club else '-'
    club_name.short_description = _('Club')

    def display_name_admin(self, obj):
        """Muestra el nombre con indentación si es una variante"""
        if obj.parent_team:
            return f"  └─ {obj.display_name_with_variant}"
        return obj.name
    display_name_admin.short_description = _('Nombre')

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
    variant_indicator.short_description = _('Variante')

    def players_count(self, obj):
        """Muestra el número de jugadores activos usando nueva estructura Person-Role"""
        return obj.identity.player_roles.filter(is_active=True).count() if obj.identity_id else 0
    players_count.short_description = _('Jugadores')
    
    def staff_count(self, obj):
        """Muestra el número de miembros del staff activos usando nueva estructura Person-Role"""
        return obj.identity.staff_roles.filter(is_active=True).count() if obj.identity_id else 0
    staff_count.short_description = _('Staff')
    
    def logo_preview(self, obj):
        """Muestra preview del logo del equipo o club"""
        logo_url = obj.display_logo
        if logo_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 3px;" />',
                logo_url
            )
        return '-'
    logo_preview.short_description = _('Logo')
    
    @admin.action(description=_('Asignar identidad común a los equipos seleccionados'))
    def assign_identity(self, request, queryset):
        try:
            identity, count = assign_common_identity(list(queryset))
        except IdentityAssignError as e:
            self.message_user(request, str(e), level='ERROR')
            return
        self.message_user(
            request,
            _('%(count)s equipo(s) asignados a la identidad «%(identity)s»')
            % {'count': count, 'identity': identity},
        )
        clubs = sorted({str(t.club or _('sin club')) for t in identity.teams.select_related('club')})
        if len(clubs) > 1:
            # Se permite (equipo inscrito en otro club federativo, #452), pero se
            # avisa por si la selección fue un error.
            self.message_user(
                request,
                _('La identidad «%(identity)s» agrupa equipos de clubes distintos: %(clubs)s. '
                  'Todos ellos podrán ver y editar las fichas de su plantilla. '
                  'Si no es el mismo equipo, reasigna la identidad en cada equipo.')
                % {'identity': identity, 'clubs': ', '.join(clubs)},
                level='WARNING',
            )

    def match_to_clubs(self, request, queryset):
        """Acción para hacer matching automático de equipos seleccionados"""
        from django.core.management import call_command
        from io import StringIO
        
        teams_without_club = queryset.filter(club__isnull=True)
        if not teams_without_club.exists():
            self.message_user(request, _('Todos los equipos seleccionados ya tienen club asignado'))
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
                self.message_user(request, _('Se asociaron %(count)s equipo(s) con clubes') % {'count': matched_count})
            else:
                self.message_user(request, _('No se pudieron hacer matches automáticos'))
                
        except Exception as e:
            self.message_user(request, _('Error durante matching: %(error)s') % {'error': e}, level='ERROR')
    
    match_to_clubs.short_description = _("Hacer matching automático con clubes")
    
    def activate_teams(self, request, queryset):
        """Acción para activar equipos seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        if updated:
            self.message_user(request, _('%(count)s equipo(s) activado(s) correctamente.') % {'count': updated})
        else:
            self.message_user(request, _('Todos los equipos seleccionados ya estaban activos.'))
    activate_teams.short_description = _("Activar equipos seleccionados")
    
    def deactivate_teams(self, request, queryset):
        """Acción para desactivar equipos seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        if updated:
            self.message_user(request, _('%(count)s equipo(s) desactivado(s) correctamente.') % {'count': updated})
            self.message_user(request, _('Los partidos de estos equipos se marcarán como retirados en el próximo scraping.'), level='WARNING')
        else:
            self.message_user(request, _('Todos los equipos seleccionados ya estaban inactivos.'))
    deactivate_teams.short_description = _("Desactivar equipos seleccionados")
