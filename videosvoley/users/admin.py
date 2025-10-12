from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


def approve_users(modeladmin, request, queryset):
    """Acción para aprobar usuarios seleccionados"""
    count = queryset.update(is_approved=True, is_active=True)
    modeladmin.message_user(request, f'{count} usuario(s) aprobado(s) correctamente.')


def reject_users(modeladmin, request, queryset):
    """Acción para rechazar usuarios seleccionados (desactiva la cuenta)"""
    count = queryset.filter(is_approved=False).update(is_active=False)
    modeladmin.message_user(request, f'{count} usuario(s) rechazado(s) correctamente. Sus cuentas han sido desactivadas.')


approve_users.short_description = "✅ Aprobar usuarios seleccionados"
reject_users.short_description = "❌ Rechazar usuarios seleccionados (desactiva cuenta)"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'parent_info_short', 'children_count', 'approval_status', 'calendar_sync_status', 'is_staff', 'date_joined']
    list_filter = ['is_approved', 'calendar_sync_enabled', 'is_staff', 'is_superuser', 'is_active', 'date_joined', 'preferred_categories']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'parent_info']
    filter_horizontal = ['preferred_categories', 'children']
    
    actions = [approve_users, reject_users]
    
    # Añadir is_approved y parent_info a los fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Aprobación', {'fields': ('is_approved',)}),
        ('Información Familiar', {'fields': ('parent_info', 'children')}),
        ('Preferencias', {'fields': ('preferred_categories',)}),
        ('Google Calendar', {'fields': ('calendar_sync_enabled', 'google_calendar_id', 'calendar_last_sync')}),
        ('Información adicional', {'fields': ('avatar',)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Aprobación', {'fields': ('is_approved',)}),
        ('Información Familiar', {'fields': ('parent_info', 'children')}),
        ('Preferencias', {'fields': ('preferred_categories',)}),
        ('Google Calendar', {'fields': ('calendar_sync_enabled', 'google_calendar_id')}),
        ('Información adicional', {'fields': ('avatar',)}),
    )
    
    def approval_status(self, obj):
        """Muestra el estado de aprobación con iconos"""
        if obj.is_approved:
            return format_html(
                '<span style="color: green; font-weight: bold;">✅ Aprobado</span>'
            )
        elif not obj.is_active and not obj.is_approved:
            return format_html(
                '<span style="color: #e74c3c; font-weight: bold;">❌ Rechazado</span>'
            )
        else:
            return format_html(
                '<span style="color: orange; font-weight: bold;">⏳ Pendiente</span>'
            )
    
    approval_status.short_description = 'Estado de Aprobación'
    approval_status.admin_order_field = 'is_approved'
    
    def parent_info_short(self, obj):
        """Muestra información familiar resumida"""
        if obj.parent_info:
            # Limitar a 50 caracteres
            info = obj.parent_info[:50]
            if len(obj.parent_info) > 50:
                info += '...'
            return info
        return format_html('<span style="color: gray; font-style: italic;">No especificado</span>')
    
    parent_info_short.short_description = 'Información Familiar'
    parent_info_short.admin_order_field = 'parent_info'
    
    def calendar_sync_status(self, obj):
        """Muestra el estado de sincronización con Google Calendar"""
        if obj.calendar_sync_enabled:
            if obj.has_google_calendar_permissions():
                if obj.calendar_last_sync:
                    return format_html(
                        '<span style="color: green; font-weight: bold;">📅 Activo</span><br>'
                        '<small style="color: gray;">Últ: {}</small>',
                        obj.calendar_last_sync.strftime('%d/%m %H:%M')
                    )
                else:
                    return format_html(
                        '<span style="color: orange; font-weight: bold;">📅 Pendiente</span>'
                    )
            else:
                return format_html(
                    '<span style="color: red; font-weight: bold;">📅 Sin permisos</span>'
                )
        else:
            return format_html(
                '<span style="color: gray;">❌ Deshabilitado</span>'
            )
    
    calendar_sync_status.short_description = 'Google Calendar'
    calendar_sync_status.admin_order_field = 'calendar_sync_enabled'
    
    def children_count(self, obj):
        """Muestra el número de hijos que puede editar este usuario"""
        count = obj.children.count()
        if count > 0:
            return format_html(
                '<span style="color: #27ae60; font-weight: bold;">👨‍👩‍👧‍👦 {} hijo{}</span>',
                count,
                's' if count != 1 else ''
            )
        return format_html('<span style="color: gray;">—</span>')
    
    children_count.short_description = 'Hijos'
    children_count.admin_order_field = 'children__count'