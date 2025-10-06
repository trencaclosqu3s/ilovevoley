from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from allauth.socialaccount.signals import social_account_added
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

User = get_user_model()


def send_notification_email(subject, template_name, context, recipient_list=None):
    """
    Envía email de notificación usando template HTML
    """
    if not settings.NOTIFICATION_EMAIL_ENABLED:
        return False
    
    if not recipient_list:
        recipient_list = settings.ADMIN_EMAIL_LIST
    
    if not recipient_list or not settings.EMAIL_HOST_USER:
        print(f"Email no enviado: {subject} - No hay destinatarios o configuración de email")
        return False
    
    try:
        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        print(f"Email enviado: {subject} a {', '.join(recipient_list)}")
        return True
    except Exception as e:
        print(f"Error enviando email: {subject} - {str(e)}")
        return False


@receiver(user_signed_up)
def user_signed_up_handler(request, user, **kwargs):
    """
    Maneja el registro de nuevos usuarios (tanto OAuth como registro normal)
    Los usuarios se crean sin aprobación por defecto
    """
    user.is_approved = False
    user.save()
    print(f"Nuevo usuario registrado: {user.username} - Pendiente de aprobación")
    
    # Enviar email de notificación a admins
    if settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
        context = {
            'user': user,
            'site_name': 'VideosVoley',
            'admin_url': f'{request.build_absolute_uri("/admin/users/user/")}{user.id}/change/',
        }
        send_notification_email(
            subject=f'Nuevo usuario pendiente de aprobación: {user.username}',
            template_name='emails/new_user_pending.html',
            context=context
        )


@receiver(social_account_added)
def social_account_added_handler(request, sociallogin, **kwargs):
    """
    Maneja específicamente cuando se añade una cuenta social (Google OAuth)
    """
    user = sociallogin.user
    if not user.is_approved:
        user.is_approved = False
        user.save()
        print(f"Usuario OAuth creado: {user.username} - Pendiente de aprobación")
        
        # Enviar email de notificación a admins (mismo que registro normal)
        if settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
            context = {
                'user': user,
                'site_name': 'VideosVoley',
                'admin_url': f'{request.build_absolute_uri("/admin/users/user/")}{user.id}/change/',
                'is_oauth': True,
            }
            send_notification_email(
                subject=f'Nuevo usuario OAuth pendiente de aprobación: {user.username}',
                template_name='emails/new_user_pending.html',
                context=context
            )


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
                    'site_name': 'VideosVoley',
                    'site_url': 'http://localhost:8000',  # Configurar según dominio
                }
                send_notification_email(
                    subject='Tu cuenta ha sido aprobada en VideosVoley',
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