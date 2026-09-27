# Detección inteligente de modificaciones federativas y control de cambios de jornada

Fecha: 2026-09-27
Issue: #135

## Objetivo

Automatizar la detección de variaciones de última hora en partidos oficiales (cambios de fecha/hora, pista/pabellón, aplazamientos o discrepancias de tanteo) comparando los datos federativos scrapeados frente al estado local antes de sobreescribir, registrando un log de auditoría (`MatchChangeLog`), ofreciendo un panel de revisión para directores de club y notificando automáticamente por email ante modificaciones de última hora.

## 1. Modelo `MatchChangeLog`

Ubicado en `ilovevoley/competitions/models/competitions.py` (tabla `videos_matchchangelog`):

- `match`: FK a `Match` (`on_delete=models.CASCADE`, `related_name='change_logs'`).
- `change_type`: `CharField` con choices:
  - `datetime`: Cambio de fecha u hora del partido.
  - `venue`: Cambio de pabellón o dirección de juego (`venue`, `field_address`, `city`).
  - `status`: Cambio de estado (`postponed`, `cancelled`, reactivación).
  - `score`: Discrepancia o modificación en el resultado (`home_score`, `away_score`).
  - `other`: Otras modificaciones técnicas (árbitros, etc.).
- `field_name`: `CharField(max_length=50)` (ej. `'match_date'`, `'venue'`, `'home_score'`).
- `old_value`: `TextField(blank=True)` (representación en texto del valor previo).
- `new_value`: `TextField(blank=True)` (representación en texto del nuevo valor federativo).
- `is_last_minute`: `BooleanField(default=False, db_index=True)` (calculado al detectar: `True` si el partido estaba programado para disputarse dentro de los 7 días posteriores al instante de detección: `now <= match_date <= now + 7d`).
- `detected_at`: `DateTimeField(auto_now_add=True, db_index=True)`.
- `notified`: `BooleanField(default=False, db_index=True)`.
- `notified_at`: `DateTimeField(null=True, blank=True)`.
- `reviewed`: `BooleanField(default=False, db_index=True)`.
- `reviewed_by`: FK a `settings.AUTH_USER_MODEL` (`null=True, blank=True, on_delete=models.SET_NULL`).
- `reviewed_at`: `DateTimeField(null=True, blank=True)`.

### Manager y Tenancy
- `MatchChangeLogQuerySet(TenantQuerySet)` con manager `MatchChangeLogManager`:
  - `for_tenant(tenant)`: filtra logs de partidos donde el club de la organización participa como local o visitante (`match__home_team__club=org.club` o `match__away_team__club=org.club`).

## 2. Motor de Detección de Deltas

Ubicado en `ilovevoley/competitions/services/delta_detector.py`:

- Función `detect_and_record_match_changes(match: Match, new_data: dict) -> list[MatchChangeLog]`:
  - Evalúa antes de actualizar el partido si hay deltas en:
    - `match_date`: detecta cambios de fecha/hora.
    - `venue`, `field_address`, `city`: detecta cambios de sede/pabellón.
    - `status`: detecta aplazamientos (`postponed`), cancelaciones (`cancelled`) o reactivaciones.
    - `home_score`, `away_score`: detecta discrepancias de tanteo.
  - Calcula `is_last_minute = (now <= match.match_date <= now + timedelta(days=7))` evaluado sobre la fecha original o nueva.
  - Guarda los objetos `MatchChangeLog` generados.
  - Invoca la alerta de notificación si se han producido cambios de última hora (`is_last_minute=True` y tipo `datetime`, `venue` o `status`).
- Integración en `ilovevoley/videos/scraping/federation.py`:
  - En `_process_json_matches_unified()` antes de persistir la actualización de un partido existente.
  - En `update_matches()` antes de persistir la actualización en endpoints clásicos.

## 3. Servicio de Notificaciones

Ubicado en `ilovevoley/competitions/services/notifications.py`:

- Settings y configuración:
  - `MATCH_CHANGE_NOTIFY_STAFF_ENABLED`: Boolean (default `False`).
  - `MATCH_CHANGE_TEST_RECIPIENT`: Email para pruebas (si `MATCH_CHANGE_NOTIFY_STAFF_ENABLED=False`, se envía exclusivamente a este email si está definido, o a los superusers).
- Función `notify_match_changes(logs: list[MatchChangeLog])`:
  - Agrupa los cambios por partido.
  - Si `MATCH_CHANGE_NOTIFY_STAFF_ENABLED=False`: envía el email de alerta al destinatario de prueba / admin.
  - Si `MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True`:
    - Resuelve destinatarios buscando en `StaffRole` (`role__in=['delegate', 'head_coach']`, `is_active=True`, temporada del partido) para los equipos afectados.
    - Obtiene emails de `person.email` o `person.user.email`.
    - Fallback: si un equipo carece de staff con email, añade a los usuarios con `Membership` `admin` o `manager` de la organización del club.
  - Envía email con plantilla clara (asunto con partido y tipo de cambio, tabla con valores antiguos vs nuevos, enlace directo a la ficha del partido y al panel de cambios).
  - Marca `notified=True` y `notified_at=timezone.now()`.

## 4. Panel de Revisión para Directores de Club

- **Ruta Web**: `/competitions/cambios-jornada/` (nombre de ruta `competitions:match_changes_review`).
  - Restringido a usuarios autenticados con rol `manager` o `admin` en el tenant activo.
  - Filtrado por temporada activa (`resolve_season_filter`) y por equipo.
  - Pestañas/filtros: "Pendientes de revisión" y "Todos los cambios".
  - Agrupación por jornada y partido con indicadores visuales (badgets de cambio horario, sede, aplazamiento).
  - Endpoint AJAX: `/competitions/ajax/cambios/<int:log_id>/marcar-revisado/` (POST) para marcar el log como revisado por el usuario actual.
- **Django Admin**:
  - `MatchChangeLogAdmin(ModelAdmin)` registrado en `ilovevoley/competitions/admin/competitions.py` con interfaz Unfold, filtros (`change_type`, `is_last_minute`, `notified`, `reviewed`, `detected_at`), campos de solo lectura (`detected_at`, `notified_at`, `reviewed_at`) y acción en lote para marcar como revisados.
