from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from django.utils import timezone

from ilovevoley.competitions.models import Match, MatchChangeLog

logger = logging.getLogger(__name__)

# Progresiones normales del ciclo de vida de un partido: no son alteraciones
# federativas. Tratarlas como tales generaría alertas urgentes cada fin de semana
# por cada partido finalizado, inundando el panel de revisión de managers.
_LIFECYCLE_TRANSITIONS = {
    ('scheduled', 'in_progress'),
    ('scheduled', 'finished'),
    ('in_progress', 'finished'),
}

# El scraper marca withdrawn/reactiva partidos según la presencia de los equipos en la
# federación. Ese vaivén no es una alteración real del calendario y no debe notificarse
# por email (se sigue registrando en MatchChangeLog para auditoría). Ver #235.
_NON_NOTIFIABLE_STATUS_TRANSITIONS = {
    ('withdrawn', 'scheduled'),
    ('scheduled', 'withdrawn'),
}


def _format_value(value: Any) -> str:
    """Convierte un valor a una representación legible en texto."""
    if value is None:
        return ''
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%d/%m/%Y %H:%M')
    return str(value).strip()


def _normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:

    """Asegura que un datetime sea timezone-aware."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt)
    return dt


def detect_and_record_match_changes(
    match: Match,
    new_data: Dict[str, Any],
    save_changes: bool = True
) -> List[MatchChangeLog]:
    """
    Compara los datos entrantes de la federación con el partido actual y
    registra los deltas en MatchChangeLog.
    
    Args:
        match: Instancia actual de Match en base de datos.
        new_data: Diccionario con los datos parseados del scraper.
        save_changes: Si True, persiste los logs en base de datos.
        
    Returns:
        Lista de objetos MatchChangeLog generados.
    """
    changes: List[MatchChangeLog] = []
    now = timezone.now()
    limit = now + timedelta(days=7)

    # 1. Comprobar fecha y hora (match_date)
    new_match_date = _normalize_datetime(new_data.get('match_date'))
    cur_match_date = _normalize_datetime(match.match_date)

    # Calcular si es cambio de última hora
    is_last_minute = False
    if cur_match_date and (now - timedelta(hours=2) <= cur_match_date <= limit):
        is_last_minute = True
    elif new_match_date and (now - timedelta(hours=2) <= new_match_date <= limit):
        is_last_minute = True

    if new_match_date and cur_match_date:
        # Considerar cambio si hay más de 60 segundos de diferencia
        if abs((new_match_date - cur_match_date).total_seconds()) >= 60:
            changes.append(
                MatchChangeLog(
                    match=match,
                    change_type='datetime',
                    field_name='match_date',
                    old_value=_format_value(cur_match_date),
                    new_value=_format_value(new_match_date),
                    is_last_minute=is_last_minute,
                )
            )

    # 2. Comprobar sede y pabellón (venue, field_address, city)
    venue_fields = [
        ('venue', 'venue'),
        ('field_address', 'venue'),
        ('city', 'venue'),
    ]
    for field_name, change_type in venue_fields:
        if field_name in new_data:
            new_val = (new_data.get(field_name) or '').strip()
            cur_val = (getattr(match, field_name, '') or '').strip()
            # Solo si el nuevo valor tiene contenido y es distinto del actual
            if new_val and new_val != cur_val:
                changes.append(
                    MatchChangeLog(
                        match=match,
                        change_type=change_type,
                        field_name=field_name,
                        old_value=cur_val,
                        new_value=new_val,
                        is_last_minute=is_last_minute,
                    )
                )

    # 3. Comprobar estado (status)
    if 'status' in new_data:
        new_status = new_data.get('status')
        transition = (match.status, new_status)
        if new_status and new_status != match.status and transition not in _LIFECYCLE_TRANSITIONS:
            changes.append(
                MatchChangeLog(
                    match=match,
                    change_type='status',
                    field_name='status',
                    old_value=match.status,
                    new_value=new_status,
                    is_last_minute=is_last_minute,
                )
            )

    # 4. Comprobar discrepancia de resultado (home_score, away_score)
    for score_field in ['home_score', 'away_score']:
        if score_field in new_data:
            new_score = new_data.get(score_field)
            cur_score = getattr(match, score_field)
            # Solo si ya tenía un resultado previo y el nuevo resultado es diferente
            if new_score is not None and cur_score is not None and new_score != cur_score:
                changes.append(
                    MatchChangeLog(
                        match=match,
                        change_type='score',
                        field_name=score_field,
                        old_value=str(cur_score),
                        new_value=str(new_score),
                        is_last_minute=is_last_minute,
                    )
                )

    if changes and save_changes:
        MatchChangeLog.objects.bulk_create(changes)
        logger.info(
            f"Registrados {len(changes)} cambios federativos para el partido {match.id} ({match})"
        )

        # Hook para notificaciones automáticas si hay cambios de última hora
        last_minute_changes = [
            c for c in changes
            if c.is_last_minute
            and c.change_type in ['datetime', 'venue', 'status']
            and not (
                c.change_type == 'status'
                and (c.old_value, c.new_value) in _NON_NOTIFIABLE_STATUS_TRANSITIONS
            )
        ]
        if last_minute_changes:
            try:
                from ilovevoley.competitions.services.notifications import notify_match_changes
                notify_match_changes(last_minute_changes)
            except Exception as e:
                logger.exception(f"No se pudieron despachar las notificaciones para el partido {match.id}: {e}")


    return changes
