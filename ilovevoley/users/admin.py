from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.conf import settings
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.html import format_html, mark_safe
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from .models import (
    CategoryPreference, Membership, NotificationPreference, User,
    WebPushAudit, WebPushSubscription,
)


class MembershipInline(TabularInline):
    """Membresías del usuario editables desde su ficha.

    Permite ver y gestionar de una vez todas las organizaciones a las que
    pertenece el usuario, evitando la confusión de editar una sola membresía
    desde su propio listado y creer que se está reemplazando.
    """
    model = Membership
    extra = 0
    fields = ('organization', 'role', 'is_approved', 'joined_at')
    readonly_fields = ('joined_at',)
    autocomplete_fields = ('organization',)


class CategoryPreferenceInline(TabularInline):
    """Categorías de interés del usuario, una fila por club."""
    model = CategoryPreference
    extra = 0
    fields = ('organization', 'categories')
    autocomplete_fields = ('organization',)


class NotificationPreferenceInline(TabularInline):
    """Preferencias de tipos de notificación del usuario, una fila por club y tipo."""
    model = NotificationPreference
    extra = 0
    fields = ('organization', 'notification_type', 'is_enabled')
    autocomplete_fields = ('organization',)


def approve_users(modeladmin, request, queryset):
    """Acción para aprobar usuarios seleccionados"""
    from ilovevoley.users.models import Membership
    count = queryset.update(
        is_approved=True,
        is_active=True,
        inactivity_warning_level=0,
        inactivity_warning_sent_at=None,
    )
    Membership.objects.filter(user__in=queryset, is_approved=False).update(is_approved=True)
    modeladmin.message_user(request, f'{count} usuario(s) aprobado(s) correctamente.')


def reject_users(modeladmin, request, queryset):
    """Acción para rechazar usuarios seleccionados (desactiva la cuenta)"""
    count = queryset.filter(is_approved=False).update(is_active=False)
    modeladmin.message_user(request, f'{count} usuario(s) rechazado(s) correctamente. Sus cuentas han sido desactivadas.')


approve_users.short_description = "✅ Aprobar usuarios seleccionados"
reject_users.short_description = "❌ Rechazar usuarios seleccionados (desactiva cuenta)"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ['username', 'email', 'first_name', 'last_name', 'parent_info_short', 'children_count', 'approval_status', 'is_staff', 'last_login', 'date_joined']
    list_filter = ['is_approved', 'inactivity_warning_level', 'is_staff', 'is_superuser', 'is_active', 'last_login', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'parent_info']
    filter_horizontal = ['children']
    readonly_fields = ('inactivity_warning_sent_at',)
    
    actions = [approve_users, reject_users, 'send_email_action']
    actions_detail = ['send_email_detail_action']
    actions_row = ['send_email_row_action']
    inlines = [MembershipInline, CategoryPreferenceInline, NotificationPreferenceInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            children_count_annotated=models.Count('children', distinct=True)
        )

    # Añadir is_approved, inactividad y parent_info a los fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Aprobación', {'fields': ('is_approved',)}),
        ('Inactividad', {'fields': ('inactivity_warning_level', 'inactivity_warning_sent_at')}),
        ('Información Familiar', {'fields': ('parent_info', 'children')}),
        ('Información adicional', {'fields': ('avatar',)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Aprobación', {'fields': ('is_approved',)}),
        ('Inactividad', {'fields': ('inactivity_warning_level', 'inactivity_warning_sent_at')}),
        ('Información Familiar', {'fields': ('parent_info', 'children')}),
        ('Información adicional', {'fields': ('avatar',)}),
    )
    
    def approval_status(self, obj):
        """Muestra el estado de aprobación con iconos"""
        if obj.is_approved:
            return mark_safe('<span style="color: green; font-weight: bold;">✅ Aprobado</span>')
        elif not obj.is_active and not obj.is_approved:
            return mark_safe('<span style="color: #e74c3c; font-weight: bold;">❌ Rechazado</span>')
        else:
            return mark_safe('<span style="color: orange; font-weight: bold;">⏳ Pendiente</span>')
    
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
        return mark_safe('<span style="color: gray; font-style: italic;">No especificado</span>')
    
    parent_info_short.short_description = 'Información Familiar'
    parent_info_short.admin_order_field = 'parent_info'
    
    
    def children_count(self, obj):
        """Muestra el número de hijos que puede editar este usuario"""
        count = getattr(obj, 'children_count_annotated', None)
        if count is None:
            count = obj.children.count()
        if count > 0:
            return format_html(
                '<span style="color: #27ae60; font-weight: bold;">👨‍👩‍👧‍👦 {} hijo{}</span>',
                count,
                's' if count != 1 else ''
            )
        return mark_safe('<span style="color: gray;">—</span>')

    children_count.short_description = 'Hijos'
    children_count.admin_order_field = 'children_count_annotated'

    def send_email_action(self, request, queryset):
        """Acción masiva para enviar correo a los usuarios seleccionados"""
        if 'apply' in request.POST:
            subject = request.POST.get('subject', '').strip()
            message = request.POST.get('message', '').strip()
            send_copy = bool(request.POST.get('send_copy'))

            ids = request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)
            selected_users = User.objects.filter(pk__in=ids)

            if not subject or not message:
                self.message_user(request, 'El asunto y el mensaje son obligatorios.', level=messages.ERROR)
                users_with_email = [u for u in selected_users if u.email and u.email.strip()]
                users_without_email = [u for u in selected_users if not u.email or not u.email.strip()]
                return render(request, 'admin/users/send_email_action.html', {
                    **self.admin_site.each_context(request),
                    'opts': self.model._meta,
                    'title': f'Enviar correo a {selected_users.count()} usuario(s) seleccionado(s)',
                    'users': selected_users,
                    'users_with_email': users_with_email,
                    'users_without_email': users_without_email,
                    'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
                    'action_url': request.get_full_path(),
                    'cancel_url': reverse('admin:users_user_changelist'),
                    'is_bulk': True,
                    'subject': subject,
                    'message': message,
                    'send_copy': send_copy,
                    'default_from_email': settings.DEFAULT_FROM_EMAIL,
                    'site_name': getattr(settings, 'SITE_NAME', 'I Love Voley'),
                })

            recipient_ids = list(selected_users.values_list('pk', flat=True))
            with_email_count = selected_users.exclude(email='').exclude(email__isnull=True).count()
            skipped = selected_users.count() - with_email_count

            from ilovevoley.core.email_utils import enqueue_on_commit
            from ilovevoley.core.tasks import send_admin_email_to_users_task

            enqueue_on_commit(
                send_admin_email_to_users_task,
                subject,
                message,
                recipient_ids,
                request.user.pk,
                send_copy,
            )

            if with_email_count > 0:
                copy_msg = (
                    f' (Se encoló copia a {request.user.email})'
                    if (send_copy and getattr(request.user, 'email', None))
                    else ''
                )
                self.message_user(
                    request,
                    f'Correo encolado para {with_email_count} usuario(s).{copy_msg}',
                    level=messages.SUCCESS,
                )

            if skipped > 0:
                self.message_user(
                    request,
                    f'⚠️ {skipped} usuario(s) fueron omitidos porque no tienen correo registrado.',
                    level=messages.WARNING,
                )

            return None

        users_with_email = [u for u in queryset if u.email and u.email.strip()]
        users_without_email = [u for u in queryset if not u.email or not u.email.strip()]

        return render(request, 'admin/users/send_email_action.html', {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Enviar correo a {queryset.count()} usuario(s) seleccionado(s)',
            'users': queryset,
            'users_with_email': users_with_email,
            'users_without_email': users_without_email,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'action_url': request.get_full_path(),
            'cancel_url': reverse('admin:users_user_changelist'),
            'is_bulk': True,
            'subject': '',
            'message': '',
            'send_copy': True,
            'default_from_email': settings.DEFAULT_FROM_EMAIL,
            'site_name': getattr(settings, 'SITE_NAME', 'I Love Voley'),
        })

    send_email_action.short_description = "✉️ Enviar correo a usuarios seleccionados"

    def _handle_send_email_single(self, request, object_id):
        """Maneja el envío de correo a un usuario individual desde acción de fila o detalle"""
        user = get_object_or_404(User, pk=object_id)
        is_from_row = 'send_email_row_action' in request.path
        cancel_url = reverse('admin:users_user_changelist') if is_from_row else reverse('admin:users_user_change', args=[object_id])
        success_url = cancel_url

        if request.method == 'POST' and 'apply' in request.POST:
            subject = request.POST.get('subject', '').strip()
            message = request.POST.get('message', '').strip()
            send_copy = bool(request.POST.get('send_copy'))

            if not user.email or not user.email.strip():
                self.message_user(
                    request,
                    f'El usuario {user.username} no tiene dirección de correo electrónico.',
                    level=messages.ERROR
                )
                return redirect(cancel_url)

            if not subject or not message:
                self.message_user(request, 'El asunto y el mensaje son obligatorios.', level=messages.ERROR)
                return render(request, 'admin/users/send_email_action.html', {
                    **self.admin_site.each_context(request),
                    'opts': self.model._meta,
                    'title': f'Enviar correo a {user.get_full_name() or user.username}',
                    'users': [user],
                    'users_with_email': [user],
                    'users_without_email': [],
                    'action_url': request.path,
                    'cancel_url': cancel_url,
                    'is_bulk': False,
                    'subject': subject,
                    'message': message,
                    'send_copy': send_copy,
                    'default_from_email': settings.DEFAULT_FROM_EMAIL,
                    'site_name': getattr(settings, 'SITE_NAME', 'I Love Voley'),
                })

            from ilovevoley.core.email_utils import enqueue_on_commit
            from ilovevoley.core.tasks import send_admin_email_to_users_task

            enqueue_on_commit(
                send_admin_email_to_users_task,
                subject,
                message,
                [user.pk],
                request.user.pk,
                send_copy,
            )

            copy_msg = (
                f' (Se encoló copia a {request.user.email})'
                if (send_copy and getattr(request.user, 'email', None))
                else ''
            )
            self.message_user(
                request,
                f'Correo encolado para {user.email}.{copy_msg}',
                level=messages.SUCCESS,
            )
            return redirect(success_url)

        users_with_email = [user] if (user.email and user.email.strip()) else []
        users_without_email = [] if (user.email and user.email.strip()) else [user]

        return render(request, 'admin/users/send_email_action.html', {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': f'Enviar correo a {user.get_full_name() or user.username}',
            'users': [user],
            'users_with_email': users_with_email,
            'users_without_email': users_without_email,
            'action_url': request.path,
            'cancel_url': cancel_url,
            'is_bulk': False,
            'subject': '',
            'message': '',
            'send_copy': True,
            'default_from_email': settings.DEFAULT_FROM_EMAIL,
            'site_name': getattr(settings, 'SITE_NAME', 'I Love Voley'),
        })

    @action(description="Enviar correo", icon="mail")
    def send_email_detail_action(self, request, object_id):
        return self._handle_send_email_single(request, object_id)

    @action(description="Enviar correo", icon="mail")
    def send_email_row_action(self, request, object_id):
        return self._handle_send_email_single(request, object_id)


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = ['user', 'organization', 'role', 'is_approved', 'joined_at']
    list_filter = ['organization', 'role', 'is_approved']
    search_fields = ['user__username', 'user__email']
    actions = ['approve_memberships']

    @admin.action(description='Aprobar membresías seleccionadas')
    def approve_memberships(self, request, queryset):
        user_ids = queryset.values_list('user_id', flat=True)
        count = queryset.update(is_approved=True)
        User.objects.filter(id__in=user_ids, is_approved=False).update(is_approved=True, is_active=True)
        self.message_user(request, f'{count} membresía(s) aprobada(s).')


@admin.register(WebPushSubscription)
class WebPushSubscriptionAdmin(ModelAdmin):
    list_display = ('user', 'organization', 'endpoint_truncated', 'created_at', 'updated_at')
    list_filter = ('organization', 'created_at')
    search_fields = ('user__username', 'user__email', 'endpoint', 'user_agent')
    readonly_fields = ('created_at', 'updated_at')

    def endpoint_truncated(self, obj):
        return (obj.endpoint[:60] + '...') if len(obj.endpoint) > 60 else obj.endpoint
    endpoint_truncated.short_description = 'Endpoint'


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(ModelAdmin):
    list_display = ('user', 'organization', 'notification_type', 'is_enabled', 'updated_at')
    list_filter = ('organization', 'notification_type', 'is_enabled')
    search_fields = ('user__username', 'user__email')
    autocomplete_fields = ('user', 'organization')


@admin.register(WebPushAudit)
class WebPushAuditAdmin(ModelAdmin):
    list_display = (
        'created_at',
        'organization',
        'notification_type',
        'match_id',
        'candidates_count',
        'dispatched_count',
        'failed_count',
    )
    list_filter = ('organization', 'notification_type', 'created_at')
    search_fields = ('organization__name', 'match_id')
    readonly_fields = (
        'created_at',
        'organization',
        'notification_type',
        'match_id',
        'candidates_count',
        'dispatched_count',
        'failed_count',
    )
    list_select_related = ('organization',)
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
