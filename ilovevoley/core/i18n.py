"""Idioma del destinatario para avisos fuera del ciclo de petición (Celery, emails, push).

En un worker no hay idioma activo, así que cada mensaje se compone en el idioma
de quien lo recibe: ``User.preferred_language`` o, si no ha elegido, el de
``settings.LANGUAGE_CODE``.
"""
from collections import defaultdict

from django.conf import settings
from django.utils import translation


def language_for(user) -> str:
    """Idioma de un usuario (o el por defecto si no ha elegido o es anónimo)."""
    lang = getattr(user, 'preferred_language', '') if user is not None else ''
    return lang if lang in dict(settings.LANGUAGES) else settings.LANGUAGE_CODE


def group_emails_by_language(emails) -> dict:
    """Agrupa direcciones por idioma; las que no son de un usuario usan el por defecto."""
    from django.contrib.auth import get_user_model

    emails = list(emails)
    by_email = {
        u.email.lower(): language_for(u)
        for u in get_user_model().objects.filter(email__in=emails)
    }
    groups = defaultdict(list)
    for email in emails:
        groups[by_email.get(email.lower(), settings.LANGUAGE_CODE)].append(email)
    return dict(groups)


def localized_messages(builder) -> dict:
    """Ejecuta ``builder() -> (title, body)`` una vez por idioma disponible.

    Devuelve ``{lang: {'title': ..., 'body': ...}}`` listo para serializar en una
    tarea Celery.
    """
    messages = {}
    for lang, _name in settings.LANGUAGES:
        with translation.override(lang):
            title, body = builder()
        messages[lang] = {'title': title, 'body': body}
    return messages


def push_message(builder) -> dict:
    """Argumentos ``title``/``body``/``translations`` de ``notify_web_push_organization_task``.

    ``title`` y ``body`` van en el idioma por defecto (dispositivos anónimos o sin
    traducción); ``translations`` trae el resto para quien tenga otro idioma.
    """
    translations = localized_messages(builder)
    default = translations[settings.LANGUAGE_CODE]
    return {'title': default['title'], 'body': default['body'], 'translations': translations}
