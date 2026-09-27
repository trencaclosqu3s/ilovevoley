# Detección Inteligente de Modificaciones Federativas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar la detección automática de variaciones federativas (fechas, pistas, aplazamientos, tanteos) en partidos oficiales con auditoría en `MatchChangeLog`, panel de revisión para directores de club y notificaciones por email ante modificaciones de última hora.

**Architecture:** Se introduce el modelo `MatchChangeLog` con soporte multi-tenant en `competitions`. Un servicio `delta_detector` compara el estado previo del `Match` con los datos entrantes del scraper antes de actualizar y calcula si se trata de un cambio de última hora (próximos 7 días). Si procede, un servicio `notifications` envía alertas por email respetando flags de rollout progresivo (`MATCH_CHANGE_NOTIFY_STAFF_ENABLED`). Se provee un panel web en `/competitions/cambios-jornada/` para directores del club y su correspondiente interfaz en Django Admin con Unfold.

**Tech Stack:** Django 6.0.8, PostgreSQL, Unfold Admin, Django Templates / Tailwind CSS, Pytest.

**Spec:** [docs/superpowers/specs/2026-09-27-match-change-detection-design.md](file:///Users/jamartinmari/orca/workspaces/videosvoley/feature-producto-detecci-n-inteligente-de-modifi/docs/superpowers/specs/2026-09-27-match-change-detection-design.md)

## Global Constraints

- Django version pinned to 6.0.8.
- App de dominio principal: `competitions`.
- Multi-tenancy: filtros por club del tenant (`MatchChangeLogQuerySet.for_tenant()`).
- Tests ejecutados con `--create-db` y pytest.
- Nombres de código en inglés (modelos, campos, funciones, vistas). Comunicación, docs y plantillas en castellano.
- Git: no realizar commits ni push sin confirmación previa del usuario con imputación de tiempo y número de issue (#135).

---

### Task 1: Modelo `MatchChangeLog` y QuerySet Multi-Tenant

**Files:**
- Modify: `ilovevoley/competitions/models/competitions.py`
- Modify: `ilovevoley/competitions/models/__init__.py`
- Test: `ilovevoley/competitions/tests/test_models.py`

**Interfaces:**
- Produces: `MatchChangeLog`, `MatchChangeLogQuerySet`, `MatchChangeLogManager`

- [x] **Step 1: Escribir el test que falla para el modelo y queryset**

Escribir en `ilovevoley/competitions/tests/test_models.py` pruebas unitarias para `MatchChangeLog`: creación, cálculo o asignación de campos (`change_type`, `field_name`, `old_value`, `new_value`, `is_last_minute`, `reviewed`, `notified`), y filtrado multi-tenant `for_tenant()`.

- [x] **Step 2: Ejecutar el test para comprobar que falla**

Ejecutar:
```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_models.py -k test_match_change_log --tb=short
```

- [x] **Step 3: Implementar `MatchChangeLog` y su QuerySet**

En `ilovevoley/competitions/models/competitions.py`:
- Definir `MatchChangeLogQuerySet(TenantQuerySet)` con método `for_tenant(tenant)`.
- Definir `MatchChangeLog` con los campos: `match`, `change_type`, `field_name`, `old_value`, `new_value`, `is_last_minute`, `detected_at`, `notified`, `notified_at`, `reviewed`, `reviewed_by`, `reviewed_at`.
- Reexportar en `ilovevoley/competitions/models/__init__.py`.
- Generar migración con `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations competitions`.

- [x] **Step 4: Ejecutar los tests con `--create-db` y verificar que pasan**

Ejecutar:
```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_models.py --create-db --tb=short
```

---

### Task 2: Motor de Detección de Deltas e Integración en Scraper

**Files:**
- Create: `ilovevoley/competitions/services/__init__.py`
- Create: `ilovevoley/competitions/services/delta_detector.py`
- Modify: `ilovevoley/videos/scraping/federation.py`
- Test: `ilovevoley/competitions/tests/test_delta_detector.py`

**Interfaces:**
- Produces: `detect_and_record_match_changes(match: Match, new_data: dict, save_changes: bool = True) -> list[MatchChangeLog]`
- Consumes: `Match`, `MatchChangeLog`

- [x] **Step 1: Escribir tests unitarios para detección de deltas**

Crear `ilovevoley/competitions/tests/test_delta_detector.py`:
- Test para detección de cambio de fecha/hora (`match_date`) y flag `is_last_minute`.
- Test para detección de cambio de sede (`venue`, `field_address`, `city`).
- Test para cambio de estado (`status` a `postponed`/`cancelled`).
- Test para discrepancia de resultado (`home_score`, `away_score`).
- Test de idempotencia: no generar log si los valores entrantes son idénticos a los actuales.

- [x] **Step 2: Ejecutar los tests para comprobar que fallan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_delta_detector.py --tb=short
```

- [x] **Step 3: Implementar `delta_detector.py`**

En `ilovevoley/competitions/services/delta_detector.py`:
- Función `detect_and_record_match_changes(match, new_data, save_changes=True)`.
- Comparación normalizada de valores (fechas timezone-aware, strings limpios).
- Lógica de `is_last_minute`: verificar si `now <= date <= now + 7 days`.
- Persistencia de los `MatchChangeLog`.

- [x] **Step 4: Integrar en `FederationScraper`**

En `ilovevoley/videos/scraping/federation.py`:
- En `_process_json_matches_unified()`: antes de actualizar `match`, llamar a `detect_and_record_match_changes(match, match_data)`.
- En `update_matches()`: antes de actualizar `existing_match`, llamar a `detect_and_record_match_changes(existing_match, match_data)`.

- [x] **Step 5: Ejecutar los tests de delta y scraping para verificar**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_delta_detector.py ilovevoley/videos/tests/test_scraping.py --tb=short
```

---

### Task 3: Servicio de Notificaciones con Flag Progresivo

**Files:**
- Create: `ilovevoley/competitions/services/notifications.py`
- Create: `ilovevoley/competitions/templates/competitions/emails/match_change_alert.html`
- Create: `ilovevoley/competitions/templates/competitions/emails/match_change_alert.txt`
- Modify: `ilovevoley/competitions/services/delta_detector.py`
- Test: `ilovevoley/competitions/tests/test_notifications.py`

**Interfaces:**
- Produces: `notify_match_changes(change_logs: list[MatchChangeLog]) -> int`
- Consumes: `MatchChangeLog`, `StaffRole`, `Membership`, `settings`

- [x] **Step 1: Escribir tests unitarios para las notificaciones**

Crear `ilovevoley/competitions/tests/test_notifications.py`:
- Test modo seguro (`MATCH_CHANGE_NOTIFY_STAFF_ENABLED=False`): se envía solo a la dirección de prueba o superuser.
- Test modo producción (`MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True`):
  - Resuelve emails de delegados y primeros entrenadores en la temporada del partido.
  - Fallback a managers/admins del club si no hay staff con email.
- Test marcado de `notified=True` y `notified_at`.
- Test de no re-notificación si ya está marcado como `notified=True`.

- [x] **Step 2: Ejecutar los tests para comprobar que fallan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_notifications.py --tb=short
```

- [x] **Step 3: Implementar plantillas y lógica de `notifications.py`**

- Crear `match_change_alert.html` y `match_change_alert.txt` con diseño limpio, tabla comparativa de cambios y enlaces directos al partido.
- En `ilovevoley/competitions/services/notifications.py`:
  - Recoger destinatarios según flags de configuración.
  - Generar y despachar correos usando `send_mail` / `EmailMultiAlternatives`.
  - Actualizar campos `notified` y `notified_at`.
- Integrar la llamada a `notify_match_changes()` desde `delta_detector.py` cuando haya cambios de última hora (`is_last_minute=True`).

- [x] **Step 4: Ejecutar los tests y verificar que pasan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_notifications.py --tb=short
```

---

### Task 4: Panel Web de Revisión para Directores de Club

**Files:**
- Modify: `ilovevoley/competitions/views.py`
- Modify: `ilovevoley/competitions/urls.py`
- Create: `ilovevoley/competitions/templates/competitions/match_changes_review.html`
- Test: `ilovevoley/competitions/tests/test_views.py`

**Interfaces:**
- Produces: `match_changes_review` (view), `ajax_mark_change_reviewed` (view)

- [x] **Step 1: Escribir tests para la vista y endpoint AJAX**

En `ilovevoley/competitions/tests/test_views.py`:
- Test acceso no autenticado o usuario sin rol manager/admin redirige o devuelve 403.
- Test acceso manager/admin de tenant: solo visualiza los cambios de su club (aislamiento multi-tenant).
- Test filtro por temporada y filtro por pendientes de revisar.
- Test POST AJAX para marcar cambio como revisado: actualiza `reviewed=True`, `reviewed_by` y `reviewed_at`.

- [x] **Step 2: Ejecutar tests para comprobar que fallan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_match_changes --tb=short
```

- [x] **Step 3: Implementar vistas, URLs y plantilla**

- En `ilovevoley/competitions/views.py`:
  - `match_changes_review(request)`: control de permisos de manager/admin en el tenant, filtrado por temporada con `resolve_season_filter`, paginación / agrupación.
  - `ajax_mark_change_reviewed(request, log_id)`: endpoint POST JSON con verificación de permisos sobre el tenant.
- En `ilovevoley/competitions/urls.py`: registrar rutas `cambios-jornada/` y `ajax/cambios/<int:log_id>/marcar-revisado/`.
- En `ilovevoley/competitions/templates/competitions/match_changes_review.html`: interfaz con Tailwind, badges cromáticos por tipo de alteración, botón dinámico para marcar como revisado.

- [x] **Step 4: Ejecutar tests de vistas y verificar que pasan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_views.py -k test_match_changes --tb=short
```

---

### Task 5: Interfaz en Django Admin con Unfold

**Files:**
- Modify: `ilovevoley/competitions/admin/competitions.py`
- Test: `ilovevoley/competitions/tests/test_admin.py`

**Interfaces:**
- Produces: `MatchChangeLogAdmin`

- [x] **Step 1: Escribir test para `MatchChangeLogAdmin`**

En `ilovevoley/competitions/tests/test_admin.py`:
- Test para acción en lote `mark_as_reviewed`.

- [x] **Step 2: Implementar `MatchChangeLogAdmin`**

En `ilovevoley/competitions/admin/competitions.py`:
- Registrar `MatchChangeLog` con `ModelAdmin` de Unfold.
- `list_display`, `list_filter`, `search_fields`, `readonly_fields`.
- Acción admin `mark_as_reviewed`.

- [x] **Step 3: Ejecutar tests de admin y verificar que pasan**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/tests/test_admin.py --tb=short
```

---

### Task 6: Verificación Global y Regresión

**Files:**
- Test: Todas las suites de `competitions` y `videos/scraping`.

- [x] **Step 1: Ejecutar suite de pruebas de `competitions` y `videos`**

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/competitions/ ilovevoley/videos/tests/test_scraping.py --create-db --tb=short
```

- [x] **Step 2: Comprobación de linting y estática**

Verificar que no haya syntax errors ni imports no utilizados en los archivos modificados.
