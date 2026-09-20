from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.conf import settings
from videosvoley.core.email_utils import get_moderation_recipients, send_notification_email
from videosvoley.core.tenant_utils import build_tenant_url
from videosvoley.users.models import Membership

User = get_user_model()


def send_new_user_notification(user, request, is_oauth=False):
    """
    Función auxiliar para enviar el correo de notificación de nuevo usuario.

    El aviso se limita al club en el que se registra: superusers y los
    managers/admins aprobados de ese tenant.
    """
    if not settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
        return

    tenant = getattr(request, 'tenant', None)

    context = {
        'user': user,
        'site_name': 'I Love Voley',
        'tenant': tenant,
        'is_oauth': is_oauth,
        'moderation_url': request.build_absolute_uri(reverse('core:moderation_panel')),
    }

    send_notification_email(
        subject=f'Nuevo usuario pendiente de aprobación: {user.username}',
        template_name='emails/new_user_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(tenant),
    )


@receiver(user_signed_up)
def user_signed_up_handler(request, user, **kwargs):
    """
    Maneja el registro de nuevos usuarios (tanto OAuth como registro normal)
    Los usuarios se crean sin aprobación por defecto.

    El correo de notificación se envía siempre en el alta, con el parent_info
    disponible en ese momento (en OAuth suele completarse después).
    """
    user.is_approved = False
    user.save()

    is_oauth = kwargs.get('sociallogin') is not None
    send_new_user_notification(user, request, is_oauth=is_oauth)


@receiver(post_save, sender=Membership)
def membership_pending_handler(sender, instance, created, **kwargs):
    """
    Avisa a los moderadores del club cuando un usuario ya aprobado solicita
    una membresía nueva (p. ej. se une a otro club).

    No avisa en el alta del usuario: la Membership se crea durante el registro,
    antes de guardar parent_info, y ese caso ya lo cubre el aviso de nuevo usuario.
    """
    if not created or instance.is_approved:
        return
    if not settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
        return

    user = instance.user
    if not user.is_approved:
        return

    organization = instance.organization
    context = {
        'user': user,
        'tenant': organization,
        'membership': instance,
        'site_name': 'I Love Voley',
        'moderation_url': f'{build_tenant_url(organization.slug)}core/moderacion/',
    }

    send_notification_email(
        subject=f'Nueva membresía pendiente: {user.username} en {organization.name}',
        template_name='emails/new_membership_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(organization),
    )


