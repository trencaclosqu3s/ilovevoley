from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, TabularInline

from ..models import Person, PlayerRole, StaffRole


class PlayerRoleInline(TabularInline):
    """Inline para roles de jugador en la vista de Person"""
    model = PlayerRole
    extra = 0
    fields = ('team', 'season', 'jersey_number', 'position', 'is_active', 'notes')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('team',)


class StaffRoleInline(TabularInline):
    """Inline para roles de staff en la vista de Person"""
    model = StaffRole
    extra = 0
    fields = ('team', 'season', 'role', 'is_active', 'notes')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('team',)


@admin.register(Person)
class PersonAdmin(ModelAdmin):
    """Admin para el modelo Person"""
    list_display = ('__str__', 'organization', 'age_display', 'contact_info', 'parents_info', 'is_active', 'photo_preview', 'active_teams_count')
    list_filter = ('organization', 'is_active', 'created_at', 'birth_date')
    search_fields = ('first_name', 'last_name', 'email', 'phone')
    readonly_fields = ('age_display', 'created_at', 'updated_at', 'photo_preview')
    autocomplete_fields = ('organization', 'user')
    actions = ['activate_people', 'deactivate_people']
    inlines = [PlayerRoleInline, StaffRoleInline]
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'birth_date', 'age_display', 'organization')
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

    def active_teams_count(self, obj):
        """Cuenta de equipos activos donde participa"""
        return obj.get_all_active_teams().count()
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
        return mark_safe('<span style="color: gray;">—</span>')
    parents_info.short_description = 'Padres'
    parents_info.admin_order_field = 'parents__count'

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
    list_display = ('person', 'team', 'season', 'jersey_number', 'display_position', 'is_active', 'created_at')
    list_filter = ('team', 'team__category', 'season', 'position', 'is_active', 'created_at')
    search_fields = ('person__first_name', 'person__last_name', 'team__name', 'jersey_number')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('person', 'team')
    actions = ['activate_roles', 'deactivate_roles']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('person', 'team', 'season')
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
    list_display = ('person', 'team', 'season', 'display_role', 'is_active', 'created_at')
    list_filter = ('team', 'team__category', 'season', 'role', 'is_active', 'created_at')
    search_fields = ('person__first_name', 'person__last_name', 'team__name')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('person', 'team')
    actions = ['activate_roles', 'deactivate_roles']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('person', 'team', 'season')
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
