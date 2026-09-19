from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from ..models import Player, Staff


class PlayerInline(TabularInline):
    model = Player
    extra = 0
    fields = ('first_name', 'last_name', 'jersey_number', 'position', 'is_active')
    readonly_fields = ('created_at',)


class StaffInline(TabularInline):
    model = Staff
    extra = 0
    fields = ('first_name', 'last_name', 'role', 'is_active')
    readonly_fields = ('created_at',)




class PlayerAdmin(ModelAdmin):
    list_display = ('__str__', 'team', 'position', 'age_display', 'is_active', 'photo_preview')
    list_filter = ('team', 'team__category', 'position', 'is_active', 'created_at')
    search_fields = ('first_name', 'last_name', 'jersey_number', 'team__name')
    readonly_fields = ('age_display', 'created_at', 'updated_at', 'photo_preview')
    autocomplete_fields = ('team', 'user')
    actions = ['activate_players', 'deactivate_players']
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'birth_date', 'age_display')
        }),
        ('Equipo y Posición', {
            'fields': ('team', 'jersey_number', 'position')
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
    
    def age_display(self, obj):
        """Muestra la edad del jugador"""
        if obj.age is not None:
            return f"{obj.age} años"
        return "No especificada"
    age_display.short_description = 'Edad'
    
    def photo_preview(self, obj):
        """Muestra preview de la foto"""
        if obj.photo:
            return format_html(
                '<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />',
                obj.photo.url
            )
        return 'Sin foto'
    photo_preview.short_description = 'Preview'
    
    def activate_players(self, request, queryset):
        """Activar jugadores seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} jugador(es) activado(s).')
    activate_players.short_description = "Activar jugadores seleccionados"
    
    def deactivate_players(self, request, queryset):
        """Desactivar jugadores seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} jugador(es) desactivado(s).')
    deactivate_players.short_description = "Desactivar jugadores seleccionados"


# @admin.register(Staff) - DESACTIVADO - USAR PersonAdmin y StaffRoleAdmin
class StaffAdmin(ModelAdmin):
    list_display = ('__str__', 'team', 'role', 'is_active', 'contact_info', 'photo_preview')
    list_filter = ('team', 'team__category', 'role', 'is_active', 'created_at')
    search_fields = ('first_name', 'last_name', 'team__name', 'email', 'phone')
    readonly_fields = ('created_at', 'updated_at', 'photo_preview')
    autocomplete_fields = ('team', 'user')
    actions = ['activate_staff', 'deactivate_staff']
    
    fieldsets = (
        ('Información Personal', {
            'fields': ('first_name', 'last_name')
        }),
        ('Equipo y Rol', {
            'fields': ('team', 'role')
        }),
        ('Contacto', {
            'fields': ('phone', 'email'),
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
    
    def contact_info(self, obj):
        """Muestra información de contacto"""
        contact_parts = []
        if obj.phone:
            contact_parts.append(f"📞 {obj.phone}")
        if obj.email:
            contact_parts.append(f"✉️ {obj.email}")
        return " | ".join(contact_parts) if contact_parts else "Sin contacto"
    contact_info.short_description = 'Contacto'
    
    def photo_preview(self, obj):
        """Muestra preview de la foto"""
        if obj.photo:
            return format_html(
                '<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />',
                obj.photo.url
            )
        return 'Sin foto'
    photo_preview.short_description = 'Preview'
    
    def activate_staff(self, request, queryset):
        """Activar miembros del staff seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        self.message_user(request, f'{updated} miembro(s) del staff activado(s).')
    activate_staff.short_description = "Activar miembros del staff seleccionados"
    
    def deactivate_staff(self, request, queryset):
        """Desactivar miembros del staff seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f'{updated} miembro(s) del staff desactivado(s).')
    deactivate_staff.short_description = "Desactivar miembros del staff seleccionados"


# =============================================================================
# NUEVA ESTRUCTURA: PERSON-ROLE ADMIN
# =============================================================================

