<!-- refreshed: 2026-10-22 -->
# Architecture

**Analysis Date:** 2026-10-22

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│  Browser / PWA (Tailwind + vanilla JS, es/ca)                │
│  `ilovevoley/static/js`, `ilovevoley/templates`              │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  nginx (`nginx.conf`) -> Django (`config/urls.py`)           │
│  Middleware: TenantMiddleware (subdomain -> request.tenant)  │
│  `ilovevoley/core/middleware.py`                             │
└──────┬───────────┬───────────┬───────────┬──────────┬───────┘
       ▼           ▼           ▼           ▼          ▼
┌──────────┐┌────────────┐┌─────────┐┌─────────┐┌──────────┐
│ core     ││competitions││ content ││ rosters ││ users    │
│ tenancy, ││ leagues,   ││ video,  ││ Person, ││ User,    │
│ Season   ││ Match,     ││ images  ││ roles,  ││ Membership│
│          ││ scraping   ││         ││ wrapped ││ webpush  │
└──────────┘└────────────┘└─────────┘└─────────┘└──────────┘
       │  teams (Club, Team, TeamIdentity)   videos (legacy shim)
       ▼
┌─────────────────────────────────────────────────────────────┐
│ PostgreSQL | Redis (cache + Celery broker/results)           │
│ Celery workers (queues default/media/scraping) + beat        │
│ `config/celery.py`, `config/celery_schedule.py`              │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Tenant resolution | Host subdomain -> `request.tenant` (`Organization`) | `ilovevoley/core/middleware.py`, `ilovevoley/core/tenant_utils.py` |
| Tenant ORM scoping | `.for_tenant()` querysets, `get_tenant_object_or_404` | `ilovevoley/core/tenancy.py`, `ilovevoley/core/mixins.py` |
| Seasons | `Season.objects.current()`, filter resolution | `ilovevoley/core/models.py`, `ilovevoley/core/season_utils.py` |
| Competitions | League/Match/Standing, scraping, public portal, ICS | `ilovevoley/competitions/` |
| Teams | Club, TeamIdentity, Team (variants) | `ilovevoley/teams/models/teams.py`, `ilovevoley/teams/identity.py` |
| Rosters | Person (global), PlayerRole/StaffRole, SeasonWrapped, link requests | `ilovevoley/rosters/` |
| Content | Video/Image/Comment, Vision tagging, thumbnails, album zip | `ilovevoley/content/` |
| Users | Custom User, Membership, WebPush, onboarding, allauth adapters | `ilovevoley/users/` |
| Legacy shim | 301 redirects from `/videos/`, model re-exports, periodic Celery tasks, scraping | `ilovevoley/videos/` |

## Pattern Overview

**Overall:** Django monolith, multi-tenant by subdomain (shared DB, row-level scoping), server-rendered templates, Celery for background work.

**Key Characteristics:**
- Domain apps under `ilovevoley.*`; `config/` holds project settings/urls/celery.
- Tenant is resolved per request; querysets expose `for_tenant(tenant)`; root domain (tenant `None`) yields empty querysets.
- Business logic sits in `services/` modules (competitions) or flat helper modules (`ilovevoley/teams/services.py`, `ilovevoley/content/services.py`), not in views.
- Models are split into packages with `__init__.py` re-exports (`ilovevoley/competitions/models/`, `ilovevoley/rosters/models/`).

## Layers

**Request/middleware:** `ilovevoley/core/middleware.py` (Tenant, CSP, UserLanguage, 404 tracking); order set in `config/settings.py` `MIDDLEWARE`.
**Views/URLs:** per-app `urls.py` (namespaced: `rosters`, `content`, `teams`, `competitions`, `core`, `public`, `portal`) included from `config/urls.py`. Public portal: `ilovevoley/competitions/portal_urls.py` (`/competicion/`) and `public_urls.py` (`/p/`, no login).
**Services:** `ilovevoley/competitions/services/*.py` (acta parsing, callups, delta detection, notifications, public_portal, weekend).
**Models/Querysets:** `TenantQuerySet` subclasses in `ilovevoley/core/tenancy.py`; custom managers on Match (`Match.objects` excludes `withdrawn`, `Match.all_objects` includes all).
**Tasks:** `tasks.py` per app and `ilovevoley/videos/tasks/` (`enrichment.py`, `rfevb.py`, `scraping.py`).

## Data Flow

### Primary Request Path

1. Request hits nginx -> Django; `TenantMiddleware` parses host (3 labels needed) and sets `request.tenant` (`ilovevoley/core/middleware.py:163`).
2. `config/urls.py` routes to an app view; legacy `/videos/*` redirect 301 (`ilovevoley/videos/urls.py`).
3. View resolves objects through `for_tenant`/`get_tenant_object_or_404`, filters by `Season.objects.current()` / `resolve_season_filter(request)`.
4. Template rendered from app `templates/` or `ilovevoley/templates/` (context processors in `ilovevoley/core/context_processors.py`).

### Scraping / Notification Flow

1. Celery beat (`config/celery_schedule.py`, DatabaseScheduler) fires tasks by explicit `name=`.
2. Routed by name pattern to queues `default`/`media`/`scraping` (`CELERY_TASK_ROUTES` in `config/settings.py`).
3. Scrapers (`ilovevoley/videos/scraping/`, `ilovevoley/competitions/services/`) update `Match`/`Standing`; `delta_detector.py` -> `notifications.py` -> Web Push (`ilovevoley/users/webpush.py`).

**State Management:** PostgreSQL for state; Redis cache for tenant org lookups (`ORG_CACHE_TTL` in `ilovevoley/core/tenant_utils.py`); sessions via Django.

## Key Abstractions

**Organization (tenant):** `ilovevoley/core/models.py`; has linked `club`, `default_home`, colors.
**TenantQuerySet:** `ilovevoley/core/tenancy.py` (`OrganizationTenantQuerySet`, `PersonTenantQuerySet`, ...).
**Season:** single `is_current`; `YYYY-YY`, cutoff 1 September.
**TeamIdentity vs Team:** identity persists across seasons; roles tie to identity (`docs/architecture/2026-10-08-plantilla-por-identidad-y-temporada.md`).
**Person:** global; unique (`first_name`,`last_name`,`birth_year`) (`ilovevoley/rosters/models/rosters.py`).

## Entry Points

**Web:** `config/wsgi.py` / `config/asgi.py`, `manage.py`, `entrypoint.sh` (no migrate/collectstatic).
**Celery:** `config/celery.py`.
**Health:** `/healthz` (`ilovevoley/core/views.py`).
**PWA:** `/manifest.webmanifest`, `/sw.js`, `/offline/`.

## Architectural Constraints

- **Threading:** sync WSGI request model; background work only through Celery (soft limit 600s, hard 900s, acks_late, prefetch 1).
- **Global state:** tenant organization cache in Redis; no module-level mutable singletons of note.
- **Circular imports:** avoided with function-local imports (e.g. `Team` imported inside `PersonTenantQuerySet.tenant_filter`).
- **Celery tasks:** every task has explicit `name=`; `PeriodicTask` rows depend on it.
- **Django pinned 6.0.8** until django-celery-beat supports 6.1+.
- **Dead branch:** do not revive `origin/refactor_apps`.

## Anti-Patterns

### Adding code to the legacy `videos` app

**What happens:** `ilovevoley/videos/` still holds scraping, tasks, many management commands, and re-exports of models.
**Why it's wrong:** Intended only as compatibility layer for old URLs and periodic tasks.
**Do this instead:** Put new models/views in the domain app; keep `videos` re-exports intact (migrations reference them via `ilovevoley/videos/models/__init__.py`).

### Per-view tenant checks

**What happens:** `if obj.organization != tenant: raise Http404`.
**Do this instead:** `Model.objects.for_tenant(tenant)` / `get_tenant_object_or_404` from `ilovevoley/core/tenancy.py`.

### Raw Match queries ignoring status

**Do this instead:** Use `Match.objects` or `Match.all_objects` deliberately; validate scores with `validate_volleyball_score(...)` before finishing a match.

## Error Handling

**Strategy:** Custom 400/403/404/500 handlers (`ilovevoley/core/views.py`, wired in `config/urls.py`); Sentry (`config/sentry.py`); `Error404TrackingMiddleware`; ratelimited auth views (`ilovevoley/users/views.py`, `ilovevoley/core/ratelimit_utils.py`).

## Cross-Cutting Concerns

**Logging:** `config/logging_production.py`; warning/error only, no info/debug/print.
**Validation:** forms per app (`forms.py`); domain validators in competitions.
**Authentication:** django-allauth (Google OAuth, identity only) + custom views; membership roles `admin`/`manager`/`member` (`ilovevoley/users/models.py`, `ilovevoley/core/tenant_utils.py`).
**i18n:** `es`/`ca`, catalogs in `locale/`; out-of-request messages via `ilovevoley/core/i18n.py`.

---

*Architecture analysis: 2026-10-22*
