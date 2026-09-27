from collections import defaultdict
import logging
from typing import List

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from ilovevoley.competitions.models import Match, MatchChangeLog

logger = logging.getLogger(__name__)
User = get_user_model()


def get_recipients_for_match(match: Match) -> List[str]:
    """
    Obtiene la lista de emails destinatarios para un partido con cambios.
    
    Respeta el flag de rollout progresivo MATCH_CHANGE_NOTIFY_STAFF_ENABLED:
    - Si es False: envía únicamente a MATCH_CHANGE_TEST_RECIPIENT (o superusuarios).
    - Si es True: busca delegados y entrenadores de los equipos, con fallback a managers del club.
    """
    notify_staff_enabled = getattr(settings, 'MATCH_CHANGE_NOTIFY_STAFF_ENABLED', False)
    test_recipient = getattr(settings, 'MATCH_CHANGE_TEST_RECIPIENT', None)

    if not notify_staff_enabled:
        if test_recipient:
            return [test_recipient]
        return list(
            User.objects.filter(is_superuser=True)
            .exclude(email='')
            .values_list('email', flat=True)
        )

    # Modo producción: delegados y entrenadores de los equipos
    from ilovevoley.rosters.models import StaffRole
    from ilovevoley.users.models import Membership

    recipients = set()
    teams = [t for t in (match.home_team, match.away_team) if t]

    for team in teams:
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

    return sorted(list(recipients))


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
    site_url = getattr(settings, 'SITE_URL', 'https://ilovevoley.com').rstrip('/')

    for match, logs in logs_by_match.items():
        recipients = get_recipients_for_match(match)
        if not recipients:
            logger.warning(f"No hay destinatarios para notificar cambios en el partido {match.id}")
            continue

        match_url = f"{site_url}/competitions/partidos/{match.id}/"
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
