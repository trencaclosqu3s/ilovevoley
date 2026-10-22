# Technology Stack

**Analysis Date:** 2026-10-22

## Languages

**Primary:**
- Python 3.13 (`.python-version`, `requires-python = ">=3.13,<3.14"` in `pyproject.toml`) - all backend code in `ilovevoley/` and `config/`

**Secondary:**
- Django templates + HTML (`ilovevoley/templates/`, `ilovevoley/*/templates/`) - server-rendered UI
- JavaScript (vanilla, no bundler) - `ilovevoley/static/js/`, service worker / PWA
- CSS (Tailwind compiled) - `ilovevoley/static/css/input.css` -> `ilovevoley/static/css/app.css` (committed)
- Bash - `deploy.sh`, `entrypoint.sh`

## Runtime

**Environment:**
- CPython 3.13 (Docker `python:3.13-slim`, multi-stage `builder` / `runtime` in `Dockerfile`)
- Gunicorn 26.2.0 WSGI (`config/wsgi.py`); `config/asgi.py` also exists
- Timezone `Europe/Madrid`; languages `es` and `ca`

**Package Manager:**
- uv 0.13.1 (pinned in `Dockerfile`, `.github/workflows/ci-cd.yml`, `.pre-commit-config.yaml`)
- Lockfile: `uv.lock` present and committed; no `requirements.txt`
- `uv sync --locked` fails the build if lock and `pyproject.toml` diverge
- `[tool.uv] exclude-newer = "7 days"` with per-package exceptions in `pyproject.toml`
- Prod venv at `/opt/venv`, read-only for `appuser`

## Frameworks

**Core:**
- Django 6.0.8 (pinned until `django-celery-beat` supports 6.1+) - web framework
- django-unfold 0.110.0 - admin theme (`ilovevoley/core/unfold_callbacks.py`)
- django-allauth 65.19.7 - auth + Google OAuth
- Celery 5.6.3 + django-celery-beat 2.9.0 - async/periodic tasks (`config/celery.py`, `config/celery_schedule.py`)
- django-ical 1.9.2 - ICS calendar feeds (`ilovevoley/competitions/calendar_feed.py`)
- django-ratelimit 4.1.0 - rate limiting (`ilovevoley/core/ratelimit_utils.py`)
- django-storages 1.14.6 - listed dependency; active storage is local `FileSystemStorage`

**Testing:**
- pytest 9.1.1, pytest-django 4.14.0, pytest-xdist 3.8.0 (`pytest.ini`, settings `config.settings_test`)

**Build/Dev:**
- Tailwind CSS 3.4.17 standalone binary, downloaded and SHA256-verified by `scripts/build_tailwind.py`; config `tailwind.config.js`; compiled by pre-commit hook (`.pre-commit-config.yaml`)
- bandit 1.9.4, pip-audit 2.10.1 (dev group, run in CI)
- Gitleaks (CI secret scan)

## Key Dependencies

**Critical:**
- psycopg2-binary 2.9.13 - PostgreSQL driver
- python-decouple 3.8 - env config (`env_config` in `config/settings.py`)
- redis 8.1.0 - Celery broker/result backend and Django cache
- Pillow 13.0.0 + pillow-heif 1.8.1 - image processing, HEIC support (needs `libheif-dev`, `libde265-dev`)
- google-cloud-vision 3.16.0, google-auth 2.62.0 - image moderation/tagging
- pywebpush 2.5.0 - Web Push (VAPID) in `ilovevoley/users/webpush.py`
- sentry-sdk[django] 2.72.0 - error tracking (`config/sentry.py`)
- requests 2.34.2, beautifulsoup4 4.15.0 - federation scraping
- pypdf >=6.21.1 - PDF parsing (match sheets / documents)
- PyJWT 2.15.1, cryptography 50.0.2 - Google ID token verification, crypto
- unidecode 1.4.0 - text normalization

**Infrastructure:**
- gunicorn 26.2.0 - app server (3 workers, timeout 30 in `docker-compose.yml`)
- Frontend CDN libs (loaded from templates): notyf@3 (jsdelivr), cropperjs 1.6.1 (cdnjs)

## Configuration

**Environment:**
- Env via `python-decouple` (`env_config(...)` in `config/settings.py`); `.env` loaded via `env_file` in compose (file present locally, never read)
- Key vars: `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_*`, `REDIS_URL`, `REDIS_RESULT_URL`, `REDIS_CACHE_URL`, `TENANT_BASE_DOMAIN`, `SENTRY_*`, `VAPID_*`, `EMAIL_*`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_VISION_ENABLED`, `GEMINI_API_KEY`, `LLM_NARRATIVE_*`
- `DB_PASSWORD` required when `DEBUG=False`
- Test settings: `config/settings_test.py`
- Security headers: CSP via `SECURE_CSP` (Django native CSP) in `config/settings.py`; HSTS, SSL redirect default on when not DEBUG

**Build:**
- `Dockerfile` (multi-stage, user `appuser` uid 1000, code owned by root)
- `docker-compose.yml` (production), `docker-compose.dev.yml` (dev)
- `nginx.conf` (reverse proxy, bad-URI blocking, gzip)
- `pyproject.toml`, `uv.lock`, `tailwind.config.js`, `pytest.ini`, `.pre-commit-config.yaml`
- `orca.yaml` (worktree setup/archive scripts)

## Platform Requirements

**Development:**
- Docker + Docker Compose; commands via `docker compose -f docker-compose.dev.yml run --rm web python manage.py <cmd>`
- Local tenants need `*.lvh.me:8008` host and `TENANT_BASE_DOMAIN=lvh.me:8008`
- `gettext` for `compilemessages`; non-ASCII worktree paths break `docker compose build`

**Production:**
- Single Docker Compose host (project `videosvoley`) with services: `db` (postgres:18-alpine), `redis` (redis:8-alpine), `web` (gunicorn), `celery-default`, `celery-media`, `celery-scraping`, `celery-beat` (DatabaseScheduler), `nginx` (nginx:alpine)
- Media at `/opt/videosvoley/media`, static at `/opt/videosvoley/static`, Postgres data at `/opt/videosvoley/postgres`
- Deploy with `./deploy.sh` (git pull, build, migrate, collectstatic, compilemessages, health check, rollback)
- Celery queues: `default`, `media`, `scraping` (`CELERY_TASK_ROUTES` in `config/settings.py`)

---

*Stack analysis: 2026-10-22*
