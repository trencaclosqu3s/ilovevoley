from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Person, PlayerRole, StaffRole, PersonManager, PlayerRoleManager, StaffRoleManager


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'age_display', 'contact_info', 'is_active', 
        'created_at'
    ]
    list_filter = ['is_active', 'created_at', 'updated_at']
    search_fields = ['first_name', 'last_name', 'email', 'phone']
    readonly_fields = ['created_at', 'updated_at', 'photo_preview']
    ordering = ['last_name', 'first_name']
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'birth_date', 'photo', 'photo_preview')
        }),
        ('Contacto', {
            'fields': ('email', 'phone', 'user'),
            'classes': ('collapse',)
        }),
        ('Estado', {
            'fields': ('is_active', 'notes'),
            'classes': ('collapse',)
        }),
        ('Estadísticas', {
            'fields': (),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_persons', 'deactivate_persons', 'export_contact_info']
    
    def activate_persons(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} personas activadas.')
    activate_persons.short_description = 'Activar personas seleccionadas'
    
    def deactivate_persons(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} personas desactivadas.')
    deactivate_persons.short_description = 'Desactivar personas seleccionadas'
    
    def export_contact_info(self, request, queryset):
        # Esta funcionalidad se implementaría con un comando de exportación
        self.message_user(request, f'Información de contacto de {queryset.count()} personas preparada para exportar.')
    export_contact_info.short_description = 'Exportar información de contacto'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('player_roles', 'staff_roles')


@admin.register(PlayerRole)
class PlayerRoleAdmin(admin.ModelAdmin):
    list_display = [
        'person', 'team', 'jersey_number', 'display_position', 
        'is_active', 'team_category', 'created_at'
    ]
    list_filter = ['is_active', 'position', 'team__category', 'created_at']
    search_fields = ['person__first_name', 'person__last_name', 'team__name']
    readonly_fields = ['created_at', 'updated_at', 'team_category']
    ordering = ['team', 'jersey_number', 'person__last_name']
    
    fieldsets = (
        ('Información del Rol', {
            'fields': ('person', 'team', 'jersey_number', 'position', 'is_active')
        }),
        ('Detalles', {
            'fields': ('team_category', 'notes'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_roles', 'deactivate_roles', 'assign_jersey_numbers']
    
    def activate_roles(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} roles de jugador activados.')
    activate_roles.short_description = 'Activar roles seleccionados'
    
    def deactivate_roles(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} roles de jugador desactivados.')
    deactivate_roles.short_description = 'Desactivar roles seleccionados'
    
    def assign_jersey_numbers(self, request, queryset):
        # Lógica para asignar números de dorsal automáticamente
        self.message_user(request, f'Asignación automática de dorsales para {queryset.count()} roles.')
    assign_jersey_numbers.short_description = 'Asignar números de dorsal automáticamente'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('person', 'team', 'team__category')


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = [
        'person', 'team', 'display_role', 'is_active', 
        'team_category', 'created_at'
    ]
    list_filter = ['is_active', 'role', 'team__category', 'created_at']
    search_fields = ['person__first_name', 'person__last_name', 'team__name']
    readonly_fields = ['created_at', 'updated_at', 'team_category']
    ordering = ['team', 'role', 'person__last_name']
    
    fieldsets = (
        ('Información del Rol', {
            'fields': ('person', 'team', 'role', 'is_active')
        }),
        ('Detalles', {
            'fields': ('team_category', 'notes'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_roles', 'deactivate_roles', 'promote_to_head_coach']
    
    def activate_roles(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} roles de staff activados.')
    activate_roles.short_description = 'Activar roles seleccionados'
    
    def deactivate_roles(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} roles de staff desactivados.')
    deactivate_roles.short_description = 'Desactivar roles seleccionados'
    
    def promote_to_head_coach(self, request, queryset):
        # Lógica para promover a entrenador principal
        self.message_user(request, f'Promoción a entrenador principal para {queryset.count()} roles.')
    promote_to_head_coach.short_description = 'Promover a entrenador principal'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('person', 'team', 'team__category')


class PlayerRoleInline(admin.TabularInline):
    """Inline para mostrar roles de jugador en el admin de personas"""
    model = PlayerRole
    extra = 0
    fields = ['team', 'jersey_number', 'position', 'is_active']
    readonly_fields = ['team_category']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('team', 'team__category')


class StaffRoleInline(admin.TabularInline):
    """Inline para mostrar roles de staff en el admin de personas"""
    model = StaffRole
    extra = 0
    fields = ['team', 'role', 'is_active']
    readonly_fields = ['team_category']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('team', 'team__category')


# Agregar inlines a PersonAdmin
PersonAdmin.inlines = [PlayerRoleInline, StaffRoleInline]


class RosterAdmin(admin.ModelAdmin):
    """Admin personalizado para gestión de plantillas"""
    list_display = ['team', 'players_count', 'staff_count', 'last_updated']
    list_filter = ['team__category']
    search_fields = ['team__name']
    
    def players_count(self, obj):
        return obj.player_roles.filter(is_active=True).count()
    players_count.short_description = 'Jugadores'
    
    def staff_count(self, obj):
        return obj.staff_roles.filter(is_active=True).count()
    staff_count.short_description = 'Staff'
    
    def last_updated(self, obj):
        return obj.updated_at
    last_updated.short_description = 'Última actualización'
    
    def get_queryset(self, request):
        from videosvoley.videos.models import Team
        return Team.objects.prefetch_related('rosters_player_roles', 'rosters_staff_roles')


# Registrar admin personalizado para plantillas
# Nota: Team se importará dinámicamente cuando se necesite
# admin.site.register(Team, RosterAdmin)  # Comentado hasta que se actualice la foreign key