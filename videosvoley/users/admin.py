from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User


def approve_users(modeladmin, request, queryset):
    """Acción para aprobar usuarios seleccionados"""
    count = queryset.update(is_approved=True)
    modeladmin.message_user(request, f'{count} usuario(s) aprobado(s) correctamente.')


def reject_users(modeladmin, request, queryset):
    """Acción para rechazar usuarios seleccionados"""
    count = queryset.update(is_approved=False)
    modeladmin.message_user(request, f'{count} usuario(s) rechazado(s) correctamente.')


approve_users.short_description = "✅ Aprobar usuarios seleccionados"
reject_users.short_description = "❌ Rechazar usuarios seleccionados"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'approval_status', 'is_staff', 'date_joined']
    list_filter = ['is_approved', 'is_staff', 'is_superuser', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    actions = [approve_users, reject_users]
    
    # Añadir is_approved a los fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Aprobación', {'fields': ('is_approved',)}),
        ('Información adicional', {'fields': ('avatar',)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Aprobación', {'fields': ('is_approved',)}),
        ('Información adicional', {'fields': ('avatar',)}),
    )
    
    def approval_status(self, obj):
        """Muestra el estado de aprobación con iconos"""
        if obj.is_approved:
            return format_html(
                '<span style="color: green; font-weight: bold;">✅ Aprobado</span>'
            )
        else:
            return format_html(
                '<span style="color: red; font-weight: bold;">⏳ Pendiente</span>'
            )
    
    approval_status.short_description = 'Estado de Aprobación'
    approval_status.admin_order_field = 'is_approved'