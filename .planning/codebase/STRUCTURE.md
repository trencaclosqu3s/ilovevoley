# Codebase Structure

**Analysis Date:** 2026-10-22

## Directory Layout

```
epic-scoreboard/
├── config/                 # Django project: settings, urls, celery, sentry, logging
├── ilovevoley/             # Root package with domain apps
│   ├── core/               # Tenancy, Season, Category, moderation, PWA, i18n, storage
│   ├── competitions/       # League, Match, Standing, scraping services, public portal
│   ├── teams/              # Club, TeamIdentity, Team
│   ├── rosters/            # Person, PlayerRole, StaffRole, SeasonWrapped
│   ├── content/            # Video, Image, Comment, thumbnails, album zip
│   ├── users/              # User, Membership, WebPush, onboarding
│   ├── videos/             # LEGACY: redirects, re-exports, scraping, Celery tasks
│   ├── templates/          # Project-wide templates (account, admin, emails, includes, users)
│   ├── static/             # css, js, fonts, images, errors
│   └── docs/
├── locale/                 # es / ca .po files (.mo gitignored)
├── docs/                   # ai-guidelines/, architecture/ (ADRs), superpowers/
├── scripts/                # build_tailwind.py, icon generation
├── Dockerfile, docker-compose.yml, docker-compose.dev.yml, nginx.conf
├── entrypoint.sh, deploy.sh
├── pyproject.toml, uv.lock, pytest.ini, tailwind.config.js
├── AGENTS.md / CLAUDE.md / GEMINI.md
└── manage.py
```

## Directory Purposes

**`config/`:**
- Key files: `settings.py`, `settings_test.py`, `urls.py`, `celery.py`, `celery_schedule.py`, `sentry.py`, `logging_production.py`.

**`ilovevoley/core/`:**
- Key files: `middleware.py`, `tenancy.py`, `tenant_utils.py`, `mixins.py`, `models.py` (Season, Category, Organization), `season_utils.py`, `i18n.py`, `protected_media.py`, `storage.py`, `services/season_wizard.py`, `moderation_views.py`, `urls.py`, `views.py`.

**`ilovevoley/competitions/`:**
- `models/` (`competitions.py`, `callups.py`, `circulars.py`, `news.py`, `story.py`), `services/` (acta_*, callup_*, delta_detector, notifications, public_portal, weekend, where_plays...), `admin/`, `views.py`, `portal_views.py` + `portal_urls.py` (`/competicion/`), `public_urls.py` (`/p/`), `calendar_feed.py`, `tasks.py`, `management/commands/`.

**`ilovevoley/teams/`:** `models/teams.py`, `identity.py`, `services.py`, `views.py`, `urls.py`.

**`ilovevoley/rosters/`:** `models/rosters.py`, `models/legacy.py`, `season_wrapped.py`, `wrapped_render.py`, `player_card.py`, `link_requests.py`, `views.py`.

**`ilovevoley/content/`:** `models/content.py`, `services.py`, `thumbnails.py`, `album_zip.py`, `views_album_zip.py`, `favorites.py`, `image_naming.py`, `tasks.py`.

**`ilovevoley/users/`:** single-file `models.py`, `views.py`, `adapters.py`, `webpush.py`, `onboarding.py`, `season_highlights.py`, `signals.py`, `tokens.py`, `tasks.py`.

**`ilovevoley/videos/`:** `urls.py` (301 redirects), `models/` (re-export shims), `scraping/` (`federation.py`, `rfevb.py`, `acta.py`, `parsers.py`), `tasks/` (`enrichment.py`, `rfevb.py`, `scraping.py`), `management/commands/` (scrape_*, fix_*, setup_league...), `views/` and `forms/` packages.

## Key File Locations

**Entry Points:**
- `manage.py`, `config/wsgi.py`, `config/asgi.py`, `config/celery.py`, `entrypoint.sh`

**Configuration:**
- `config/settings.py`, `config/settings_test.py`, `pytest.ini`, `pyproject.toml`, `tailwind.config.js`, `nginx.conf`

**Core Logic:**
- `ilovevoley/core/tenancy.py`, `ilovevoley/competitions/services/`, `ilovevoley/rosters/models/rosters.py`

**Testing:**
- `ilovevoley/<app>/tests/` (see below), guide in `docs/ai-guidelines/testing-guidelines.md`

## Naming Conventions

**Files:** snake_case modules; tests `test_<topic>.py` (e.g. `ilovevoley/competitions/tests/test_acta_review.py`); templates snake_case, partials prefixed `_` (`_standings_table.html`).
**Directories:** lowercase app names; models/admin/services split into packages when large.
**Code:** English identifiers; Spanish for docs/issues/comments; Celery tasks named in snake_case via explicit `name=`.
**URLs:** namespaced per app (`app_name`); public Spanish paths (`donde-juega/`, `competicion/`, `finde/`).

## Where to Add New Code

**New feature:** the matching domain app (never `videos`). Models in `<app>/models/`, logic in `<app>/services/` (or `services.py`), views in `<app>/views.py`, routes in `<app>/urls.py`, templates in `<app>/templates/<app>/`.
**New tenant-scoped model:** add a `TenantQuerySet` subclass in `ilovevoley/core/tenancy.py` style and use `.for_tenant()`.
**New Celery task:** `<app>/tasks.py` with explicit `name=`; add queue route in `CELERY_TASK_ROUTES` (`config/settings.py`) and schedule in `config/celery_schedule.py`.
**Tests:** `ilovevoley/<app>/tests/test_<models|views|forms|utils|...>.py`, only if justified per testing guidelines.
**Shared templates/partials:** `ilovevoley/templates/includes/`.
**Static JS/CSS:** `ilovevoley/static/js`, `ilovevoley/static/css`.
**Translations:** `locale/<lang>/LC_MESSAGES/django.po`.
**Architecture decisions:** `docs/architecture/YYYY-MM-DD-<slug>.md`.
**Management commands:** `<app>/management/commands/`.

## Special Directories

**`locale/`:** `.po` committed, `.mo` generated (gitignored).
**`staticfiles/`:** generated by `collectstatic`, not committed.
**`ilovevoley/*/migrations/`:** generated by `makemigrations`; never edit by hand; data backfills as `RunPython` migrations.
**`.planning/`:** GSD planning artifacts.

---

*Structure analysis: 2026-10-22*
