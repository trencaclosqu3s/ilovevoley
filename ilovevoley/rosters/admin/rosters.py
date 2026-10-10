from django.contrib import admin
from django.db.models import Prefetch
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from ..models import Person, PersonOrganization, PlayerRole, StaffRole


class PersonOrganizationInline(TabularInline):
    """Pertenencias de la ficha a clubes con su estado (#478).

    Sustituye al widget M2M: con through no se puede editar la relación
    directamente y el estado (alta/baja + fechas) vive en estas filas.
    """
    model = PersonOrganization
    extra = 0
    fields = ('organization', 'is_active', 'start_date', 'end_date', 'updated_at')
    readonly_fields = ('start_date', 'updated_at')
    autocomplete_fields = ('organization',)


class PlayerRoleInline(TabularInline):
    """Inline para roles de jugador en la vista de Person"""
    model = PlayerRole
    extra = 0
    fields = ('identity', 'season', 'jersey_number', 'position', 'is_active', 'notes')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('identity',)


class StaffRoleInline(TabularInline):
    """Inline para roles de staff en la vista de Person"""
    model = StaffRole
    extra = 0
    fields = ('identity', 'season', 'role', 'is_active', 'notes')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('identity',)


class MembershipStateFilter(admin.SimpleListFilter):
    """Estado de pertenencia a algún club (#478)."""
    title = 'Pertenencia a club'
    parameter_name = 'membership'

    def lookups(self, request, model_admin):
        return (
            ('alta', 'De alta'),
            ('baja', 'De baja'),
            ('sin', 'Sin pertenencia'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'alta':
            return queryset.filter(club_memberships__is_active=True).distinct()
        if self.value() == 'baja':
            return queryset.filter(club_memberships__is_active=False).distinct()
        if self.value() == 'sin':
            return queryset.filter(club_memberships__isnull=True)
        return queryset


@admin.register(Person)
class PersonAdmin(ModelAdmin):
    """Admin para el modelo Person"""
    list_display = ('__str__', 'birth_year', 'age_display', 'contact_info', 'parents_info', 'membership_state', 'is_active', 'photo_preview', 'active_teams_count')
    list_filter = (MembershipStateFilter, 'is_active', 'image_consent', 'created_at', 'birth_date')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    readonly_fields = ('age_display', 'created_at', 'updated_at', 'photo_preview', 'image_consent_updated_at')
    autocomplete_fields = ('user',)
    actions = ['activate_people', 'deactivate_people']
    inlines = [PersonOrganizationInline, PlayerRoleInline, StaffRoleInline]

    fieldsets = (
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'birth_date', 'birth_year', 'age_display')
        }),
        ('Contacto', {
            'fields': ('email', 'phone'),
            'classes': ('collapse',)
        }),
        ('Foto', {
            'fields': ('photo', 'photo_preview'),
            'classes': ('collapse',)
        }),
        ('Usuario Vinculado', {
            'fields': ('user',),
            'classes': ('collapse',),
            'description': 'Opcional: vincular con un usuario de la plataforma'
        }),
        ('Consentimiento de imagen', {
            'fields': ('image_consent', 'image_consent_updated_at')
        }),
        ('Estado', {
            'fields': ('is_active', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def photo_preview(self, obj):
        """Muestra preview de la foto"""
        if obj.photo:
            return format_html(
                '<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />',
                obj.photo.url
            )
        return 'Sin foto'
    photo_preview.short_description = 'Preview'

    def membership_state(self, obj):
        """Estado de pertenencia a clubes: alta o baja por organización (#478)."""
        memberships = list(obj.club_memberships.all())
        if not memberships:
            return format_html('<span style="color: gray;">{}</span>', '—')
        parts = [
            format_html(
                '<span style="color: {};">{}: {}</span>',
                '#27ae60' if m.is_active else '#e74c3c',
                m.organization.name,
                'alta' if m.is_active else 'baja',
            )
            for m in memberships
        ]
        return format_html('<br>'.join(['{}'] * len(parts)), *parts)
    membership_state.short_description = 'Clubes'

    def active_teams_count(self, obj):
        """Cuenta de equipos activos donde participa"""
        return obj.get_active_identities().count()
    active_teams_count.short_description = 'Equipos Activos'
    
    def parents_info(self, obj):
        """Muestra información sobre los padres que pueden editar esta ficha"""
        parents = obj.parents.all()
        if parents.exists():
            parent_names = [parent.get_full_name() or parent.username for parent in parents]
            return format_html(
                '<span style="color: #27ae60; font-weight: bold;">👨‍👩‍👧‍👦 {} padre{}</span><br><small style="color: gray;">{}</small>',
                parents.count(),
                's' if parents.count() != 1 else '',
                ', '.join(parent_names)
            )
        return format_html('<span style="color: gray;">{}</span>', '—')
    parents_info.short_description = 'Padres'
    parents_info.admin_order_field = 'parents__count'

    def get_queryset(self, request):
        """Prefetch de pertenencias (con organización) para el changelist (#478)."""
        return super().get_queryset(request).prefetch_related(
            Prefetch(
                'club_memberships',
                queryset=PersonOrganization.objects.select_related('organization').order_by('organization__name'),
            )
        )

    def activate_people(self, request, queryset):
        """Activar personas seleccionadas"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} persona(s) activada(s).')
    activate_people.short_description = "Activar personas seleccionadas"
    
    def deactivate_people(self, request, queryset):
        """Desactivar personas seleccionadas"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} persona(s) desactivada(s).')
    deactivate_people.short_description = "Desactivar personas seleccionadas"


@admin.register(PlayerRole)
class PlayerRoleAdmin(ModelAdmin):
    """Admin para el modelo PlayerRole"""
    list_display = ('person', 'identity', 'season', 'jersey_number', 'display_position', 'is_active', 'created_at')
    list_filter = ('identity', 'identity__category', 'season', 'position', 'is_active', 'created_at')
    search_fields = ('person__first_name', 'person__last_name', 'identity__core_name', 'jersey_number')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('person', 'identity')
    actions = ['activate_roles', 'deactivate_roles']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('person', 'identity', 'season')
        }),
        ('Detalles del Jugador', {
            'fields': ('jersey_number', 'position')
        }),
        ('Estado', {
            'fields': ('is_active', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def activate_roles(self, request, queryset):
        """Activar roles seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} rol(es) de jugador activado(s).')
    activate_roles.short_description = "Activar roles seleccionados"
    
    def deactivate_roles(self, request, queryset):
        """Desactivar roles seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} rol(es) de jugador desactivado(s).')
    deactivate_roles.short_description = "Desactivar roles seleccionados"


@admin.register(StaffRole)
class StaffRoleAdmin(ModelAdmin):
    """Admin para el modelo StaffRole"""
    list_display = ('person', 'identity', 'season', 'display_role', 'is_active', 'created_at')
    list_filter = ('identity', 'identity__category', 'season', 'role', 'is_active', 'created_at')
    search_fields = ('person__first_name', 'person__last_name', 'identity__core_name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('person', 'identity')
    actions = ['activate_roles', 'deactivate_roles']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('person', 'identity', 'season')
        }),
        ('Detalles del Staff', {
            'fields': ('role',)
        }),
        ('Estado', {
            'fields': ('is_active', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def activate_roles(self, request, queryset):
        """Activar roles seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} rol(es) de staff activado(s).')
    activate_roles.short_description = "Activar roles seleccionados"
    
    def deactivate_roles(self, request, queryset):
        """Desactivar roles seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} rol(es) de staff desactivado(s).')
    deactivate_roles.short_description = "Desactivar roles seleccionados"
