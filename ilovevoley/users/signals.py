from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.conf import settings
from ilovevoley.core.email_utils import enqueue_on_commit
from ilovevoley.core.tasks import notify_membership_pending_task, notify_new_user_pending_task
from ilovevoley.users.models import Membership

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
    moderation_url = request.build_absolute_uri(reverse('core:moderation_panel'))
    tenant_id = tenant.id if tenant is not None else None
    enqueue_on_commit(
        notify_new_user_pending_task,
        user.id,
        tenant_id,
        moderation_url,
        is_oauth,
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

    enqueue_on_commit(notify_membership_pending_task, instance.id)


@receiver(user_logged_in)
def reset_inactivity_warning_on_login(sender, request, user, **kwargs):
    """Resetea los avisos de inactividad cuando el usuario inicia sesión (#327)."""
    if getattr(user, 'inactivity_warning_level', 0) > 0 or getattr(user, 'inactivity_warning_sent_at', None) is not None:
        User.objects.filter(pk=user.pk).update(
            inactivity_warning_level=0,
            inactivity_warning_sent_at=None,
        )

