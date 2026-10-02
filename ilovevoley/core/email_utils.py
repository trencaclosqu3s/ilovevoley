"""
Utilidades comunes para envío de emails y notificaciones
"""
from django.contrib.auth import get_user_model
from django.core.mail import send_mail, EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.utils import translation
from django.utils.translation import gettext as _

from .i18n import group_emails_by_language, language_for
import os

User = get_user_model()


def enqueue_on_commit(task, *args, **kwargs):
    """Enqueue a Celery task after the current DB transaction commits."""
    def _run():
        task.delay(*args, **kwargs)

    transaction.on_commit(_run)


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


def get_moderation_recipients(tenant=None):
    """
    Destinatarios de los avisos de moderación: superusers y, cuando hay tenant,
    los managers/admins aprobados de esa organización.

    Args:
        tenant (Organization, optional): organización a la que se limita el aviso

    Returns:
        list: emails sin duplicados
    """
    emails = set(
        User.objects.filter(is_superuser=True, email__isnull=False)
        .exclude(email='')
        .values_list('email', flat=True)
    )

    if tenant is not None:
        from ilovevoley.users.models import Membership

        emails.update(
            Membership.objects.filter(
                organization=tenant,
                is_approved=True,
                role__in=['manager', 'admin'],
                user__email__isnull=False,
            ).exclude(user__email='').values_list('user__email', flat=True)
        )

    if not emails and hasattr(settings, 'ADMIN_EMAIL_LIST'):
        emails = set(settings.ADMIN_EMAIL_LIST)

    return list(emails)


def send_notification_email(subject, template_name, context, recipient_list=None, attachments=None, embedded_images=None):
    """Envía el aviso a cada destinatario en su idioma (``User.preferred_language``).

    ``subject`` puede ser un ``str`` o un callable sin argumentos que lo componga con
    el idioma activo; con un ``str`` ya traducido el asunto no cambia por destinatario.
    Devuelve ``True`` solo si todos los grupos de idioma se enviaron.
    """
    if not settings.NOTIFICATION_EMAIL_ENABLED:
        return False
    if not recipient_list:
        recipient_list = get_admin_emails()
    if not recipient_list:
        return _send_notification_email(
            subject() if callable(subject) else subject,
            template_name, context, recipient_list, attachments, embedded_images,
        )

    results = []
    for lang, emails in group_emails_by_language(recipient_list).items():
        with translation.override(lang):
            results.append(_send_notification_email(
                subject() if callable(subject) else subject,
                template_name, context, emails, attachments, embedded_images,
            ))
    return all(results)


def _send_notification_email(subject, template_name, context, recipient_list=None, attachments=None, embedded_images=None):
    """
    Envía email de notificación usando template HTML
    
    Args:
        subject (str): Asunto del email
        template_name (str): Nombre del template HTML a usar
        context (dict): Contexto para renderizar el template
        recipient_list (list, optional): Lista de destinatarios. Si no se proporciona, 
                                         se envía a todos los superusers
        attachments (list, optional): Lista de tuplas (filename, content, mimetype) o rutas de archivos
        embedded_images (dict, optional): Diccionario de imágenes embebidas {cid: filepath}
    
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
        
        # Si hay adjuntos o imágenes embebidas, usar EmailMultiAlternatives
        if attachments or embedded_images:
            from email.mime.image import MIMEImage
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipient_list
            )
            email.attach_alternative(html_message, "text/html")
            
            # Procesar imágenes embebidas (con Content-ID)
            if embedded_images:
                for cid, image_path in embedded_images.items():
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as img_file:
                            img_data = img_file.read()
                            img = MIMEImage(img_data)
                            img.add_header('Content-ID', f'<{cid}>')
                            img.add_header('Content-Disposition', 'inline', filename=os.path.basename(image_path))
                            email.attach(img)
            
            # Procesar adjuntos normales
            if attachments:
                for attachment in attachments:
                    if isinstance(attachment, tuple) and len(attachment) == 3:
                        # Formato: (filename, content, mimetype)
                        email.attach(*attachment)
                    elif isinstance(attachment, str) and os.path.exists(attachment):
                        # Formato: ruta de archivo
                        email.attach_file(attachment)
            
            email.send(fail_silently=False)
        else:
            # Sin adjuntos, usar send_mail simple
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


def send_admin_email_to_users(subject, message_body, recipients, admin_user=None, send_copy=False):
    """
    Envía correos personalizados redactados por un administrador a uno o más usuarios.
    
    Args:
        subject (str): Asunto del correo
        message_body (str): Cuerpo del mensaje
        recipients (iterable): Lista o QuerySet de usuarios (o un único usuario)
        admin_user (User, optional): Usuario administrador remitente
        send_copy (bool): Si True, envía una copia al correo del administrador
        
    Returns:
        dict: {
            'sent_count': int,
            'failed_count': int,
            'skipped_no_email_count': int,
            'errors': list of str,
            'successful_emails': list of str,
        }
    """
    import logging
    logger = logging.getLogger(__name__)

    # Normalizar recipients a lista
    if not hasattr(recipients, '__iter__') or isinstance(recipients, (str, bytes)):
        recipients = [recipients]

    site_name = getattr(settings, 'SITE_NAME', 'I Love Voley')
    from_email = settings.DEFAULT_FROM_EMAIL
    
    # Configurar Reply-To con el email del admin si está disponible
    reply_to = None
    admin_name = None
    admin_email = None
    if admin_user:
        admin_name = admin_user.get_full_name() or admin_user.username
        if getattr(admin_user, 'email', None):
            admin_email = admin_user.email
            reply_to = [f"{admin_name} <{admin_user.email}>" if admin_user.get_full_name() else admin_user.email]

    results = {
        'sent_count': 0,
        'failed_count': 0,
        'skipped_no_email_count': 0,
        'errors': [],
        'successful_emails': [],
    }

    template_name = 'emails/admin_direct_message.html'

    for user in recipients:
        user_email = getattr(user, 'email', None)
        if not user_email or not user_email.strip():
            results['skipped_no_email_count'] += 1
            continue

        user_email = user_email.strip()
        recipient_name = user.get_full_name() or user.username if hasattr(user, 'username') else user_email

        with translation.override(language_for(user)):
            admin_label = admin_name or _('Administración')
            context = {
                'site_name': site_name,
                'subject': subject,
                'recipient': user,
                'recipient_name': recipient_name,
                'message_body': message_body,
                'admin_name': admin_label,
                'admin_email': admin_email,
                'is_copy': False,
            }

            try:
                html_message = render_to_string(template_name, context)
                plain_message = _(
                    'Hola %(name)s,\n\n%(body)s\n\nAtentamente,\n%(admin)s\nAdministración de %(site)s'
                ) % {
                    'name': recipient_name,
                    'body': message_body,
                    'admin': admin_label,
                    'site': site_name,
                }
                if admin_email:
                    plain_message += _('\n\nPuedes responder directamente a este correo (%(email)s).') % {'email': admin_email}

                email = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_message,
                    from_email=from_email,
                    to=[user_email],
                    reply_to=reply_to,
                )
                email.attach_alternative(html_message, "text/html")
                email.send(fail_silently=False)

                results['sent_count'] += 1
                results['successful_emails'].append(user_email)
                logger.info(f"Correo de admin enviado a {user_email} (Asunto: {subject})")
            except Exception as e:
                error_msg = f"Error enviando a {user_email}: {str(e)}"
                logger.error(error_msg)
                results['failed_count'] += 1
                results['errors'].append(error_msg)

    # Si se solicitó copia y se envió al menos un correo
    if send_copy and admin_email and results['sent_count'] > 0:
        with translation.override(language_for(admin_user)):
            admin_name = admin_name or _('Administración')
            try:
                copy_subject = _('[Copia] %(subject)s') % {'subject': subject}
                copy_context = {
                    'site_name': site_name,
                    'subject': copy_subject,
                    'recipient_name': _('%(name)s (Copia)') % {'name': admin_name},
                    'message_body': message_body,
                    'admin_name': admin_name,
                    'admin_email': admin_email,
                    'is_copy': True,
                    'recipients_summary': ', '.join(results['successful_emails']),
                }
                html_copy = render_to_string(template_name, copy_context)
                plain_copy = _(
                    '[COPIA DE SEGURIDAD]\nMensaje enviado a: %(recipients)s\n\n'
                    '%(body)s\n\n'
                    'Atentamente,\n%(admin)s\nAdministración de %(site)s'
                ) % {
                    'recipients': ', '.join(results['successful_emails']),
                    'body': message_body,
                    'admin': admin_name,
                    'site': site_name,
                }
                copy_email = EmailMultiAlternatives(
                    subject=copy_subject,
                    body=plain_copy,
                    from_email=from_email,
                    to=[admin_email],
                )
                copy_email.attach_alternative(html_copy, "text/html")
                copy_email.send(fail_silently=False)
                logger.info(f"Copia de correo de admin enviada a {admin_email}")
            except Exception as e:
                logger.warning(f"No se pudo enviar la copia al admin {admin_email}: {str(e)}")

    return results

