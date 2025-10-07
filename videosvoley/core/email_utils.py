"""
Utilidades comunes para envío de emails y notificaciones
"""
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

User = get_user_model()


def get_admin_emails():
    """
    Obtiene dinámicamente los emails de todos los usuarios superuser
    
    Returns:
        list: Lista de emails de los superusers que tienen email configurado
    """
    admin_emails = list(
        User.objects.filter(is_superuser=True, email__isnull=False)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    
    # Si no hay superusers con email, usar fallback de ADMIN_EMAIL_LIST si existe
    if not admin_emails and hasattr(settings, 'ADMIN_EMAIL_LIST'):
        admin_emails = settings.ADMIN_EMAIL_LIST
    
    return admin_emails


def send_notification_email(subject, template_name, context, recipient_list=None):
    """
    Envía email de notificación usando template HTML
    
    Args:
        subject (str): Asunto del email
        template_name (str): Nombre del template HTML a usar
        context (dict): Contexto para renderizar el template
        recipient_list (list, optional): Lista de destinatarios. Si no se proporciona, 
                                         se envía a todos los superusers
    
    Returns:
        bool: True si el email se envió correctamente, False en caso contrario
    """
    if not settings.NOTIFICATION_EMAIL_ENABLED:
        return False
    
    # Si no se proporciona lista de destinatarios, usar emails de superusers
    if not recipient_list:
        recipient_list = get_admin_emails()
    
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
