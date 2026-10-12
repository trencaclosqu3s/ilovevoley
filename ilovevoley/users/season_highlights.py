"""Destinatarios y envío del mail puntual de novedades de temporada."""

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.finders import find
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext as _

from ilovevoley.core.email_utils import send_notification_email
from ilovevoley.core.tenant_utils import build_absolute_url
from ilovevoley.users.tokens import generate_voluntary_deactivation_token


User = get_user_model()

# Mail de producto (plataforma), no del club del destinatario.
SITE_NAME = 'I Love Voley'
LOGO_CID = 'ilovevoley_logo'
LOGO_STATIC = 'images/logo_app.png'


def season_highlights_recipients():
    """Usuarios activos, aprobados y con email (un destinatario = un mail)."""
    return (
        User.objects.filter(is_active=True, is_approved=True)
        .exclude(Q(email__isnull=True) | Q(email=''))
        .distinct()
        .order_by('id')
    )


def _primary_tenant(user):
    membership = (
        user.memberships.filter(is_approved=True)
        .select_related('organization')
        .order_by('id')
        .first()
    )
    return membership.organization if membership else None


def send_season_highlights_email(user):
    """Envía el mail de novedades 26/27 a un usuario en su idioma preferido."""
    if not user.email:
        return False

    tenant = _primary_tenant(user)
    avisos_path = reverse('profile') + '?tab=avisos#activar'
    avisos_url = build_absolute_url(avisos_path, tenant=tenant)
    token = generate_voluntary_deactivation_token(user)
    deactivation_url = build_absolute_url(
        reverse('deactivate_account', args=[token]),
        tenant=tenant,
    )
    logo_path = find(LOGO_STATIC)
    embedded_images = {LOGO_CID: logo_path} if logo_path else None

    return send_notification_email(
        subject=lambda: _('Novedades I Love Voley · temporada 26/27'),
        template_name='emails/season_highlights.html',
        context={
            'user': user,
            'site_name': SITE_NAME,
            'logo_cid': LOGO_CID if logo_path else None,
            'avisos_url': avisos_url,
            'deactivation_url': deactivation_url,
        },
        recipient_list=[user.email],
        embedded_images=embedded_images,
    )
