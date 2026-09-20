from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.urls import reverse
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added
from django.contrib.auth import get_user_model
from django.conf import settings
from videosvoley.core.email_utils import get_moderation_recipients, send_notification_email

User = get_user_model()


def send_new_user_notification(user, request, is_oauth=False):
    """
    Función auxiliar para enviar el correo de notificación de nuevo usuario.
    Se llama cuando el usuario ya tiene parent_info completado.

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
    
    subject_type = 'OAuth' if is_oauth else 'tradicional'
    send_notification_email(
        subject=f'Nuevo usuario pendiente de aprobación: {user.username}',
        template_name='emails/new_user_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(tenant),
    )
    print(f"Correo de notificación enviado para usuario {user.username} (tipo: {subject_type})")


@receiver(user_signed_up)
def user_signed_up_handler(request, user, **kwargs):
    """
    Maneja el registro de nuevos usuarios (tanto OAuth como registro normal)
    Los usuarios se crean sin aprobación por defecto
    
    NOTA: El correo de notificación NO se envía aquí, sino cuando el usuario
    completa el parent_info en la vista pending_approval o en el formulario de registro.
    """
    user.is_approved = False
    user.save()
    print(f"Nuevo usuario registrado: {user.username} - Pendiente de aprobación")
    
    # Para registro tradicional (no OAuth), el parent_info ya está guardado
    # por el CustomSignupForm, así que enviamos el correo inmediatamente
    if user.parent_info:
        send_new_user_notification(user, request, is_oauth=False)


@receiver(social_account_added)
def social_account_added_handler(request, sociallogin, **kwargs):
    """
    Maneja específicamente cuando se añade una cuenta social (Google OAuth)
    
    NOTA: El correo de notificación NO se envía aquí porque el usuario OAuth
    necesita completar el parent_info primero en la vista pending_approval.
    El correo se enviará desde esa vista cuando guarde el parent_info.
    """
    user = sociallogin.user
    if not user.is_approved:
        user.is_approved = False
        user.save()
        print(f"Usuario OAuth creado: {user.username} - Pendiente de aprobación (esperando parent_info)")


@receiver(post_save, sender=User)
def user_approved_handler(sender, instance, created, **kwargs):
    """
    Envía email al usuario cuando es aprobado
    """
    if not created and instance.is_approved:
        # Verificar si cambió de no aprobado a aprobado
        if hasattr(instance, '_old_is_approved') and not instance._old_is_approved:
            print(f"Usuario aprobado: {instance.username}")
            
            # Enviar email al usuario
            if settings.EMAIL_NOTIFICATIONS.get('user_approved', True) and instance.email:
                context = {
                    'user': instance,
                    'site_name': 'I Love Voley',
                    'site_url': 'http://localhost:8000',  # Configurar según dominio
                }
                send_notification_email(
                    subject='Tu cuenta ha sido aprobada en I Love Voley',
                    template_name='emails/user_approved.html',
                    context=context,
                    recipient_list=[instance.email]
                )


# Hook para trackear cambios en is_approved
@receiver(post_save, sender=User)
def track_user_approval_changes(sender, instance, **kwargs):
    """
    Trackea cambios en el estado de aprobación del usuario
    """
    if hasattr(instance, '_old_is_approved'):
        del instance._old_is_approved

