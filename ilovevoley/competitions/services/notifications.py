from collections import defaultdict
import logging
from typing import List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _, gettext_noop

from ilovevoley.core.i18n import group_emails_by_language, push_message
from ilovevoley.competitions.models import CallUpPlayer, Match, MatchChangeLog
from ilovevoley.competitions.services.branches import match_branches, organization_branch_q
from ilovevoley.core.tenant_utils import build_absolute_url

logger = logging.getLogger(__name__)
User = get_user_model()


def _dispatch_organization_push(
    orgs, *, build, url: str, category_ids: List[int], notification_type: str, match_id: Optional[int] = None
) -> int:
    """Programa el push de cada organización tras el commit de la transacción actual.

    Devuelve cuántas organizaciones se encolaron. Concentra aquí el bucle que
    antes se repetía igual en resultado, cambios y recordatorio. ``build`` devuelve
    ``(título, cuerpo)`` y se ejecuta una vez por idioma para avisar a cada
    dispositivo en el de su usuario.
    """
    from django.db import transaction
    from ilovevoley.users.tasks import notify_web_push_organization_task

    message = push_message(build)
    sent = 0
    for org in orgs:
        kwargs = {
            'organization_id': org.id,
            **message,
            'url': url,
            'category_ids': category_ids,
            'notification_type': notification_type,
            'match_id': match_id,
        }
        transaction.on_commit(lambda kw=kwargs: notify_web_push_organization_task.delay(**kw), robust=True)
        sent += 1
    return sent


def _superuser_emails() -> List[str]:
    """Emails de los superusuarios con dirección configurada."""
    return list(
        User.objects.filter(is_superuser=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )


def _clubs_with_notifications_disabled(club_ids: set) -> set:
    """Clubes cuyas organizaciones tienen todas los avisos desactivados.

    Una sola consulta para todos los clubes del partido. Un club sin organizaciones
    vinculadas no aparece aquí: no tiene configuración que lo silencie. Un ``club_ids``
    vacío devuelve un queryset vacío sin tocar la BD.
    """
    from ilovevoley.core.models import Organization

    flags_by_club = defaultdict(list)
    for club_id, enabled in (
        Organization.objects
        .filter(club_id__in=club_ids)
        .values_list('club_id', 'notify_match_changes')
    ):
        flags_by_club[club_id].append(enabled)

    return {club_id for club_id, flags in flags_by_club.items() if not any(flags)}


def _clubs_without_match_branch(match, club_ids):
    """Clubes con organizaciones activas que no cubren ninguna rama del partido.

    Un club sin ninguna organización activa no se bloquea: no tiene configuración
    de ramas que lo silencie (mismo criterio que los avisos desactivados).
    """
    from ilovevoley.core.models import Organization

    if not club_ids:
        return set()
    q = organization_branch_q(match_branches(match))
    if q is None:
        return set()
    orgs = Organization.objects.filter(club_id__in=club_ids, is_active=True)
    clubs_with_org = set(orgs.values_list('club_id', flat=True))
    covered = set(orgs.filter(q).values_list('club_id', flat=True))
    return clubs_with_org - covered


def get_recipients_for_match(match: Match) -> List[str]:
    """
    Obtiene la lista de emails destinatarios para un partido con cambios.

    Respeta el flag de rollout progresivo MATCH_CHANGE_NOTIFY_STAFF_ENABLED:
    - Si es False: envía únicamente a MATCH_CHANGE_TEST_RECIPIENT (y a los superusuarios
      si MATCH_CHANGE_NOTIFY_SUPERUSERS está activo).
    - Si es True: busca delegados y entrenadores de los equipos con avisos activos, con
      fallback a managers del club, más una copia global a los superusuarios.
    """
    notify_staff_enabled = getattr(settings, 'MATCH_CHANGE_NOTIFY_STAFF_ENABLED', False)
    test_recipient = getattr(settings, 'MATCH_CHANGE_TEST_RECIPIENT', None)
    notify_superusers = getattr(settings, 'MATCH_CHANGE_NOTIFY_SUPERUSERS', True)
    superuser_emails = set(_superuser_emails()) if notify_superusers else set()

    if not notify_staff_enabled:
        recipients = {test_recipient} if test_recipient else set()
        return sorted(recipients | superuser_emails)

    # Modo producción: delegados y entrenadores de los equipos
    from ilovevoley.rosters.models import StaffRole
    from ilovevoley.users.models import Membership

    recipients = set(superuser_emails)
    teams = [t for t in (match.home_team, match.away_team) if t]

    # Clubes que han desactivado los avisos desde su organización (una sola consulta)
    disabled_clubs = _clubs_with_notifications_disabled(
        {t.club_id for t in teams if t.club_id}
    )

    branch_blocked_clubs = _clubs_without_match_branch(
        match, {t.club_id for t in teams if t.club_id}
    )

    for team in teams:
        if team.club_id in disabled_clubs or team.club_id in branch_blocked_clubs:
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

        # Un correo por idioma, cada uno en el del destinatario. Preservar la privacidad
        # entre clubes rivales y miembros del staff usando BCC.
        groups_sent = 0
        for lang, lang_recipients in group_emails_by_language(recipients).items():
            try:
                with translation.override(lang):
                    subject = _('[Aviso de Partido] Modificación federativa: %(home)s vs %(away)s') % {
                        'home': match.home_team_display,
                        'away': match.away_team_display,
                    }
                    html_content = render_to_string('competitions/emails/match_change_alert.html', context)
                    text_content = render_to_string('competitions/emails/match_change_alert.txt', context)

                if len(lang_recipients) == 1:
                    to_emails = lang_recipients
                    bcc_emails = []
                else:
                    to_emails = [from_email]
                    bcc_emails = lang_recipients

                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=from_email,
                    to=to_emails,
                    bcc=bcc_emails,
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send(fail_silently=False)
                groups_sent += 1
            except Exception as e:
                logger.error(
                    f"Error al enviar notificación de cambios ({lang}) para partido {match.id}: {e}",
                    exc_info=True,
                )

        # Con envío parcial se marcan igualmente: reintentar reenviaría a quien ya lo recibió.
        if groups_sent:
            log_ids = [log.pk for log in logs]
            MatchChangeLog.objects.filter(pk__in=log_ids).update(notified=True, notified_at=now)
            sent_count += 1

    return sent_count


def match_category_ids(match: Match) -> List[int]:
    """Categorías de un partido: las de la liga y las de ambos equipos."""
    ids = {c.id for c in match.league.categories.all()} if match.league else set()
    for team in (match.home_team, match.away_team):
        if team and team.category_id:
            ids.add(team.category_id)
    return list(ids)


def format_match_result_body(match: Match) -> str:
    """Construye el texto descriptivo del resultado con parciales si existen."""
    from ilovevoley.competitions.services.sets import match_set_scores

    scores = match_set_scores(match)
    if scores:
        sets_str = ", ".join(f"{h}-{a}" for h, a in scores)
        return _("Marcador final: %(result)s (%(sets)s)") % {
            'result': match.result_display,
            'sets': sets_str,
        }
    return _("Marcador final: %(result)s") % {'result': match.result_display}


def notify_match_result(match: Match, tenant=None) -> bool:
    """Avisa por Web Push a los clubes de un resultado final con parciales.

    - Idempotente: comprueba y actualiza `result_notified_at` para no repetir el aviso.
    - Destinatarios: si se especifica `tenant`, se avisa a ese club. Si no (p. ej. scraping),
      se avisa a todas las organizaciones vinculadas a los clubes de los equipos del partido.
    - Envío en `transaction.on_commit(..., robust=True)`.
    """
    if not match.is_finished or match.home_score is None or match.away_score is None:
        return False

    # Idempotencia atómica: si ya fue notificado, salir sin enviar
    updated = Match.objects.filter(pk=match.pk, result_notified_at__isnull=True).update(
        result_notified_at=timezone.now()
    )
    if not updated:
        return False

    match.result_notified_at = timezone.now()

    # Determinar organizaciones a notificar
    from ilovevoley.core.models import Organization

    q = organization_branch_q(match_branches(match))
    if tenant:
        orgs = Organization.objects.filter(pk=tenant.pk)
    else:
        club_ids = {t.club_id for t in (match.home_team, match.away_team) if t and t.club_id}
        orgs = Organization.objects.filter(club_id__in=club_ids, is_active=True)
    if q is not None:
        orgs = orgs.filter(q)

    if not orgs:
        return True

    def build():
        title = _("Resultado: %(home)s vs %(away)s") % {
            'home': match.home_team_display, 'away': match.away_team_display,
        }
        return title, format_match_result_body(match)

    _dispatch_organization_push(
        orgs,
        build=build,
        url=reverse('competitions:match_detail', args=[match.id]),
        category_ids=match_category_ids(match),
        notification_type='match_result',
        match_id=match.id,
    )

    return True


# Etiqueta legible de cada campo de sede en el cuerpo del push: los tres comparten
# `change_type='venue'`, así que sin el `field_name` todo salía como "Nueva pista".
_VENUE_FIELD_LABELS = {
    'venue': gettext_noop('pista'),
    'field_address': gettext_noop('dirección'),
    'city': gettext_noop('localidad'),
}


def format_match_change_push(match: Match, changes: List[MatchChangeLog]) -> tuple:
    """Construye el título y cuerpo del push para modificaciones de partido."""
    home_name = match.home_team_display
    away_name = match.away_team_display
    teams_vs = f"{home_name} vs {away_name}"
    teams_dash = f"{home_name} - {away_name}"

    has_postponed = any(c.change_type == 'status' and c.new_value == 'postponed' for c in changes)
    has_cancelled = any(c.change_type == 'status' and c.new_value == 'cancelled' for c in changes)
    has_datetime = any(c.change_type == 'datetime' for c in changes)
    has_venue = any(c.change_type == 'venue' for c in changes)

    # Título
    if has_postponed:
        title = _("Partido aplazado: %(teams)s") % {'teams': teams_vs}
    elif has_cancelled:
        title = _("Partido suspendido: %(teams)s") % {'teams': teams_vs}
    elif has_datetime and has_venue:
        title = _("Cambio de horario y pista: %(teams)s") % {'teams': teams_vs}
    elif has_datetime:
        title = _("Cambio de horario: %(teams)s") % {'teams': teams_vs}
    elif has_venue:
        title = _("Cambio de pista: %(teams)s") % {'teams': teams_vs}
    else:
        title = _("Modificación de partido: %(teams)s") % {'teams': teams_vs}

    # Cuerpo
    details = []
    if has_postponed:
        details.append(_("El partido %(teams)s ha sido aplazado") % {'teams': teams_dash})
    elif has_cancelled:
        details.append(_("El partido %(teams)s ha sido suspendido") % {'teams': teams_dash})
    else:
        details.append(_("Modificación en el partido %(teams)s") % {'teams': teams_dash})

    change_items = []
    for c in changes:
        if c.change_type == 'datetime':
            change_items.append(_("Nueva fecha/hora: %(value)s") % {'value': c.new_value})
        elif c.change_type == 'venue':
            label = _(_VENUE_FIELD_LABELS.get(c.field_name, 'pista'))
            change_items.append(_("Nueva %(label)s: %(value)s") % {'label': label, 'value': c.new_value})

    if change_items:
        body = f"{details[0]}. {'. '.join(change_items)}."
    else:
        body = f"{details[0]}."

    return title, body


def notify_match_change_push(match: Match, changes: List[MatchChangeLog]) -> bool:
    """Avisa por Web Push de cambios de fecha/hora, pista o aplazamiento.

    - Requiere el flag `MATCH_CHANGE_PUSH_ENABLED=True`.
    - Agrupa todos los cambios del partido en una única notificación push.
    - Notifica a organizaciones activas vinculadas a los clubes del partido que tengan
      `notify_match_changes=True`.
    - Envía con `transaction.on_commit(..., robust=True)` y `notification_type='match_change'`.
    """
    from django.conf import settings
    if not getattr(settings, 'MATCH_CHANGE_PUSH_ENABLED', False):
        return False

    if not changes:
        return False

    from ilovevoley.core.models import Organization

    club_ids = {t.club_id for t in (match.home_team, match.away_team) if t and t.club_id}
    if not club_ids:
        return False

    orgs = Organization.objects.filter(
        club_id__in=club_ids,
        is_active=True,
        notify_match_changes=True,
    )
    q = organization_branch_q(match_branches(match))
    if q is not None:
        orgs = orgs.filter(q)

    return _dispatch_organization_push(
        orgs,
        build=lambda: format_match_change_push(match, changes),
        url=reverse('competitions:match_detail', args=[match.id]),
        category_ids=match_category_ids(match),
        notification_type='match_change',
        match_id=match.id,
    ) > 0


def notify_match_reminder(match: Match) -> bool:
    """Envía un recordatorio push 2 horas antes del partido a los clubes implicados.

    - Idempotente: comprueba y actualiza `reminder_sent_at` para no repetir el aviso.
    - Excluye partidos finalizados, aplazados, cancelados o retirados.
    - Respeta categorías y tipo de notificación 'match_reminder' (#277).
    - Envía a las organizaciones activas asociadas a los clubes del partido.
    - Envío en `transaction.on_commit(..., robust=True)`.
    """
    if match.status in ['finished', 'postponed', 'cancelled', 'withdrawn']:
        return False

    from django.db import transaction

    with transaction.atomic():
        updated = Match.objects.filter(pk=match.pk, reminder_sent_at__isnull=True).update(
            reminder_sent_at=timezone.now()
        )
        if not updated:
            return False

        match.reminder_sent_at = timezone.now()

        club_ids = {t.club_id for t in (match.home_team, match.away_team) if t and t.club_id}
        if not club_ids:
            return True

        from ilovevoley.core.models import Organization

        orgs = Organization.objects.filter(club_id__in=club_ids, is_active=True)
        q = organization_branch_q(match_branches(match))
        if q is not None:
            orgs = orgs.filter(q)

        home_name = match.home_team_display
        away_name = match.away_team_display

        def build():
            return (
                _("Recordatorio de partido: %(home)s vs %(away)s") % {'home': home_name, 'away': away_name},
                _("El partido %(home)s - %(away)s empieza en 2 h. ¡Ve preparando las rodilleras!")
                % {'home': home_name, 'away': away_name},
            )

        _dispatch_organization_push(
            orgs,
            build=build,
            url=reverse('competitions:match_detail', args=[match.id]),
            category_ids=match_category_ids(match),
            notification_type='match_reminder',
            match_id=match.id,
        )

    return True


# Con este número de fotos ya subidas el recordatorio no aporta nada.
PHOTO_REMINDER_MIN_IMAGES = 5


def notify_match_photo_reminder(match: Match) -> bool:
    """Envía un push para animar a subir fotos de un partido ya finalizado (#361).

    - Idempotente: reclama `photo_reminder_sent_at` antes de enviar.
    - No avisa si el partido ya tiene `PHOTO_REMINDER_MIN_IMAGES` fotos o más (sin contar las rechazadas)
      (en ese caso se marca igualmente para no volver a evaluarlo).
    - Respeta categorías y el tipo 'match_photos'; abre la subida con el partido preseleccionado.
    """
    from django.db import transaction

    with transaction.atomic():
        updated = Match.objects.filter(pk=match.pk, photo_reminder_sent_at__isnull=True).update(
            photo_reminder_sent_at=timezone.now()
        )
        if not updated:
            return False

        if match.images.exclude(status='rejected').count() >= PHOTO_REMINDER_MIN_IMAGES:
            return False

        club_ids = {t.club_id for t in (match.home_team, match.away_team) if t and t.club_id}
        if not club_ids:
            return False

        from ilovevoley.core.models import Organization

        orgs = Organization.objects.filter(club_id__in=club_ids, is_active=True)
        q = organization_branch_q(match_branches(match))
        if q is not None:
            orgs = orgs.filter(q)

        home_name = match.home_team_display
        away_name = match.away_team_display

        def build():
            return (
                _("¿Tienes fotos del partido?"),
                _("%(home)s - %(away)s ya ha terminado. ¡Súbelas mientras están frescas!")
                % {'home': home_name, 'away': away_name},
            )

        _dispatch_organization_push(
            orgs,
            build=build,
            url=f"{reverse('content:image_bulk_upload')}?match={match.id}",
            category_ids=match_category_ids(match),
            notification_type='match_photos',
            match_id=match.id,
        )

    return True


def notify_callup_confirmed(player: CallUpPlayer) -> bool:
    """Envía notificación Web Push a los miembros del club informando de la convocatoria confirmada."""
    if player.notification_sent:
        return False
    if not player.organization:
        return False
    if player.match_status != CallUpPlayer.STATUS_CONFIRMED:
        return False

    player.notification_sent = True
    player.save(update_fields=['notification_sent'])

    category_ids = []
    if player.person:
        category_ids = list(
            player.person.player_roles.filter(
                season=player.callup.season,
                is_active=True,
                team__category_id__isnull=False,
            ).values_list('team__category_id', flat=True).distinct()
        )

    def build():
        return (
            _("Convocatoria %(label)s: %(name)s") % {
                'label': player.callup.notification_label,
                'name': player.raw_full_name,
            },
            _("%(name)s ha sido convocado/a para %(title)s.") % {
                'name': player.raw_full_name,
                'title': player.callup.title,
            },
        )

    url = f"https://voleibolib.federatio.com/upload/descargas/{player.callup.source_url}" if player.callup.source_url else '/'

    from ilovevoley.users.tasks import notify_web_push_organization_task
    notify_web_push_organization_task.delay(
        organization_id=player.organization_id,
        **push_message(build),
        url=url,
        category_ids=category_ids,
        notification_type='callup_confirmed',
    )
    return True


def notify_callup_suspected(player: CallUpPlayer) -> bool:
    """Envía alerta Web Push a administradores y managers para moderar una convocatoria en duda."""
    if player.notification_sent:
        return False
    if not player.organization:
        return False
    if player.match_status != CallUpPlayer.STATUS_SUSPECTED:
        return False

    player.notification_sent = True
    player.save(update_fields=['notification_sent'])

    def build():
        return (
            _("Posible convocatoria detectada: %(name)s") % {'name': player.raw_full_name},
            _("Se ha detectado una posible convocatoria de %(name)s (%(club)s). Revisa y confirma en el panel.") % {
                'name': player.raw_full_name,
                'club': player.raw_club,
            },
        )

    url = '/core/moderacion/#convocatorias'

    from ilovevoley.users.tasks import notify_web_push_organization_task
    notify_web_push_organization_task.delay(
        organization_id=player.organization_id,
        **push_message(build),
        url=url,
        category_ids=[],
        notification_type='admin_alert',
    )
    return True


def notify_match_live_stream(match: Match, tenant=None) -> bool:
    """Envía notificación Web Push de retransmisión en directo (#359).

    - Idempotente: comprueba y actualiza `stream_notified_at` para no repetir el aviso.
    - Excluye partidos sin stream_url o que no estén en la ventana temporal de directo.
    - Respeta categorías y el tipo de notificación NotificationType.LIVE_STREAM.
    - Envía a las organizaciones activas asociadas a los clubes del partido (o `tenant` si se especifica).
    - Envío en `transaction.on_commit(..., robust=True)`.
    """
    if not match.stream_url or not match.is_live_window:
        return False

    from django.db import transaction
    from ilovevoley.users.models import NotificationType

    with transaction.atomic():
        updated = Match.objects.filter(pk=match.pk, stream_notified_at__isnull=True).update(
            stream_notified_at=timezone.now()
        )
        if not updated:
            return False

        match.stream_notified_at = timezone.now()

        from ilovevoley.core.models import Organization

        if tenant:
            orgs = Organization.objects.filter(pk=tenant.pk)
        else:
            club_ids = {t.club_id for t in (match.home_team, match.away_team) if t and t.club_id}
            if not club_ids:
                return True
            orgs = Organization.objects.filter(club_id__in=club_ids, is_active=True)

        q = organization_branch_q(match_branches(match))
        if q is not None:
            orgs = orgs.filter(q)

        home_name = match.home_team_display
        away_name = match.away_team_display

        def build():
            return (
                _("🔴 En directo: %(home)s vs %(away)s") % {'home': home_name, 'away': away_name},
                _("¡El partido %(home)s vs %(away)s se está emitiendo en directo! Toca para ver la retransmisión.")
                % {'home': home_name, 'away': away_name},
            )

        _dispatch_organization_push(
            orgs,
            build=build,
            url=reverse('competitions:match_detail', args=[match.id]),
            category_ids=match_category_ids(match),
            notification_type=NotificationType.LIVE_STREAM,
            match_id=match.id,
        )

    return True


