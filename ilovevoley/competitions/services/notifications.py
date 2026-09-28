from collections import defaultdict
import logging
from typing import List

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import Match, MatchChangeLog
from ilovevoley.core.tenant_utils import build_absolute_url

logger = logging.getLogger(__name__)
User = get_user_model()


def _superuser_emails() -> List[str]:
    """Emails de los superusuarios con dirección configurada."""
    return list(
        User.objects.filter(is_superuser=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )


def _team_notifications_enabled(team) -> bool:
    """Avisos activados para el club del equipo.

    Un club sin organizaciones vinculadas no tiene configuración, así que no se
    silencia. Si todas sus organizaciones tienen los avisos desactivados, el equipo
    no genera avisos.
    """
    club = getattr(team, 'club', None)
    if club is None:
        return True
    orgs = club.organizations.all()
    return not orgs.exists() or orgs.filter(notify_match_changes=True).exists()


def get_recipients_for_match(match: Match) -> List[str]:
    """
    Obtiene la lista de emails destinatarios para un partido con cambios.
    
    Respeta el flag de rollout progresivo MATCH_CHANGE_NOTIFY_STAFF_ENABLED:
    - Si es False: envía únicamente a MATCH_CHANGE_TEST_RECIPIENT (y a los superusuarios).
    - Si es True: busca delegados y entrenadores de los equipos con avisos activos, con
      fallback a managers del club, más una copia global a los superusuarios
      (MATCH_CHANGE_NOTIFY_SUPERUSERS).
    """
    notify_staff_enabled = getattr(settings, 'MATCH_CHANGE_NOTIFY_STAFF_ENABLED', False)
    test_recipient = getattr(settings, 'MATCH_CHANGE_TEST_RECIPIENT', None)
    superuser_emails = set(_superuser_emails())

    if not notify_staff_enabled:
        recipients = {test_recipient} if test_recipient else set()
        return sorted(recipients | superuser_emails)

    # Modo producción: delegados y entrenadores de los equipos
    from ilovevoley.rosters.models import StaffRole
    from ilovevoley.users.models import Membership

    recipients = set(superuser_emails) if getattr(settings, 'MATCH_CHANGE_NOTIFY_SUPERUSERS', True) else set()
    teams = [t for t in (match.home_team, match.away_team) if t]

    for team in teams:
        # El club puede haber desactivado los avisos desde su organización
        if not _team_notifications_enabled(team):
            continue

        team_recipients = set()
        staff_qs = StaffRole.objects.filter(
            team=team,
            role__in=['delegate', 'head_coach'],
            is_active=True,
        )
        if match.league and match.league.season:
            staff_qs = staff_qs.filter(season=match.league.season)

        for staff in staff_qs.select_related('person', 'person__user'):
            if staff.person.email:
                team_recipients.add(staff.person.email)
            if staff.person.user and staff.person.user.email:
                team_recipients.add(staff.person.user.email)

        # Fallback: si el equipo no tiene miembros de staff con email, buscar managers/admins del club
        if not team_recipients and team.club:
            managers = Membership.objects.filter(
                organization__club=team.club,
                role__in=['admin', 'manager'],
                is_approved=True,
            ).select_related('user')
            for m in managers:
                if m.user and m.user.email:
                    team_recipients.add(m.user.email)

        recipients.update(team_recipients)

    return sorted(recipients)


def _organizations_by_club(matches):
    """Mapa ``club_id -> Organization`` de los clubes implicados en el lote.

    Una sola consulta para todo el lote evita el N+1 al construir la URL de cada
    partido. Si un club tuviera varias organizaciones activas se conserva la
    primera por nombre (mismo criterio que el anterior ``.first()``).
    """
    from ilovevoley.core.models import Organization

    club_ids = {
        club_id
        for match in matches
        for team in (match.home_team, match.away_team)
        if (club_id := getattr(team, 'club_id', None))
    }
    if not club_ids:
        return {}
    by_club = {}
    for org in (
        Organization.objects
        .filter(club_id__in=club_ids, is_active=True)
        .only('id', 'slug', 'club_id')
        .order_by('name')
    ):
        by_club.setdefault(org.club_id, org)
    return by_club


def _match_organization(match, organizations_by_club):
    """Organización del club implicado, para enlazar con el subdominio correcto.

    Un partido puede enfrentar clubes de dos organizaciones (o ninguna: club sin
    tenant vinculado). Se prioriza la del local y, si no la tiene, la del visitante.
    """
    for team in (match.home_team, match.away_team):
        org = organizations_by_club.get(getattr(team, 'club_id', None))
        if org is not None:
            return org
    return None


def notify_match_changes(change_logs: List[MatchChangeLog]) -> int:
    """
    Envía notificaciones por email agrupadas por partido para cambios aún no notificados.
    
    Args:
        change_logs: Lista de instancias de MatchChangeLog.
        
    Returns:
        Número de emails enviados.
    """
    unnotified = [log for log in change_logs if not log.notified]
    if not unnotified:
        return 0

    logs_by_match = defaultdict(list)
    for log in unnotified:
        logs_by_match[log.match].append(log)

    sent_count = 0
    now = timezone.now()
    notify_staff_enabled = getattr(settings, 'MATCH_CHANGE_NOTIFY_STAFF_ENABLED', False)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@ilovevoley.com')
    organizations_by_club = _organizations_by_club(list(logs_by_match.keys()))

    for match, logs in logs_by_match.items():
        recipients = get_recipients_for_match(match)
        if not recipients:
            logger.warning(f"No hay destinatarios para notificar cambios en el partido {match.id}")
            continue

        match_path = reverse('competitions:match_detail', kwargs={'match_id': match.id})
        # Enlace al subdominio del club (evita caer en la landing del dominio raíz).
        # Sin club vinculado, build_absolute_url usa el dominio base con la ruta correcta.
        match_url = build_absolute_url(match_path, tenant=_match_organization(match, organizations_by_club))
        context = {
            'match': match,
            'changes': logs,
            'is_test_mode': not notify_staff_enabled,
            'match_url': match_url,
            'site_name': 'I Love Voley',
        }

        subject = f"[Aviso de Partido] Modificación federativa: {match.home_team_display} vs {match.away_team_display}"
        html_content = render_to_string('competitions/emails/match_change_alert.html', context)
        text_content = render_to_string('competitions/emails/match_change_alert.txt', context)

        try:
            # Preservar la privacidad entre clubes rivales y miembros del staff usando BCC
            if len(recipients) == 1:
                to_emails = recipients
                bcc_emails = []
            else:
                to_emails = [from_email]
                bcc_emails = recipients

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=to_emails,
                bcc=bcc_emails,
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)

            # Marcar logs como notificados en bloque
            log_ids = [log.pk for log in logs]
            MatchChangeLog.objects.filter(pk__in=log_ids).update(notified=True, notified_at=now)

            sent_count += 1
            logger.info(f"Notificación de cambios enviada para partido {match.id} a {len(recipients)} destinatarios")

        except Exception as e:
            logger.error(f"Error al enviar notificación de cambios para partido {match.id}: {e}", exc_info=True)

    return sent_count
