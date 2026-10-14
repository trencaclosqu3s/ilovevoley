"""Checklist de bienvenida familiar (#533).

Guía corta de primeros pasos para que la aprobación de la cuenta se convierta
en uso recurrente. El estado de cada paso sale de métodos que ya existen en
``User``; este módulo solo decide el orden, el destino y cuándo la guía deja de
tener sentido (completada o descartada).
"""
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def onboarding_steps(user, tenant, *, categories=None, push=None):
    """Estado real de cada paso de la guía, en orden de presentación.

    ``categories`` y ``push`` permiten reutilizar el estado que el context
    processor ya ha consultado; sin ellos se calculan aquí. El vínculo con la
    ficha propia o de un hijo lo resuelve ``User.has_my_profile``, cacheado por
    la navbar en cada petición.
    """
    return [
        {
            'key': 'categories',
            'icon': 'target',
            'label': _('Elige tus equipos y categorías'),
            'url': f"{reverse('profile')}?tab=avisos",
            'done': user.has_preferred_categories(tenant) if categories is None else categories,
        },
        {
            'key': 'push',
            'icon': 'bell',
            'label': _('Activa los avisos en este móvil'),
            'url': f"{reverse('profile')}?tab=avisos#activar",
            'done': user.has_push_subscription(tenant) if push is None else push,
        },
        {
            'key': 'profile',
            'icon': 'link',
            'label': _('Vincula tu ficha y la de tus hijos'),
            'url': reverse('rosters:my_profile'),
            'done': user.has_my_profile,
        },
        {
            'key': 'calendar',
            'icon': 'calendar',
            'label': _('Suscribe el calendario de partidos'),
            'url': f"{reverse('profile')}?tab=calendario",
            'done': bool(user.calendar_token),
        },
    ]


def welcome_checklist(user, tenant, *, categories=None, push=None):
    """Pasos a mostrar en la guía de bienvenida, o ``None`` si no toca.

    No hay guía sin club activo, si el usuario ya la descartó, o si ha
    completado los cuatro pasos. Al completarla o descartarla no vuelve a
    aparecer: la persistencia es por cuenta, no por dispositivo.
    """
    if tenant is None or user.onboarding_dismissed_at is not None:
        return None
    steps = onboarding_steps(user, tenant, categories=categories, push=push)
    if all(step['done'] for step in steps):
        return None
    return steps
