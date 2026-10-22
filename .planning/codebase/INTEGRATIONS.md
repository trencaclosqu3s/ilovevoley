# External Integrations

**Analysis Date:** 2026-10-22

## APIs & External Services

**Federation scraping (volleyball data):**
- voleibolib (`www.voleibolib.net`, `voleibolib.federatio.com`) - fixtures, results, standings
  - Client: `requests` + `beautifulsoup4`; code in `ilovevoley/videos/scraping/`, `ilovevoley/competitions/services/`; endpoints modelled by `ScrapingEndpoint` (`ilovevoley/competitions/models/`)
  - Auth: none (public pages)
- RFEVB (`intranet.rfevb.com`) - federative data via `ilovevoley/videos/rfevb_service.py`
- Docs: `ilovevoley/docs/SCRAPING.md`, `ilovevoley/docs/SCRAPING_AVANZADO.md`
- Tasks run on the Celery `scraping` queue

**AI / LLM:**
- Google Gemini (`generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`)
  - Acta (match sheet) vision parsing: `ilovevoley/competitions/services/acta_vision.py`; env `GEMINI_API_KEY`, `GEMINI_ACTA_MODEL`, `ACTA_VISION_ENABLED`
  - Season narrative generation: `ilovevoley/core/narrative.py`; env `LLM_NARRATIVE_ENABLED`, `LLM_NARRATIVE_API_KEY`, `LLM_NARRATIVE_MODEL`, `LLM_NARRATIVE_TIMEOUT`, `LLM_NARRATIVE_MIN_INTERVAL`
  - SDK/Client: plain `requests` calls

**Image moderation:**
- Google Cloud Vision API - automatic tagging/moderation of images
  - SDK/Client: `google-cloud-vision`, `google-auth`; code in `ilovevoley/content/services.py`
  - Auth: service-account JSON file mounted at `/app/voley-474111-a4a6b029e20b.json` (present in repo root, git-ignored) via `GOOGLE_APPLICATION_CREDENTIALS`; optional `GOOGLE_CREDENTIALS_JSON`; toggles `GOOGLE_VISION_ENABLED`, `AUTO_MODERATION_ENABLED`

**Video embeds:**
- YouTube (`www.youtube.com`, `www.youtube-nocookie.com`, thumbnails `img.youtube.com`, `i.ytimg.com`) - embedded iframes for `Video` (see `ilovevoley/docs/VIDEOS_YOUTUBE.md`); allowed in CSP `frame-src`/`img-src`

**Frontend CDNs (CSP-allowlisted):**
- `cdn.jsdelivr.net` (notyf@3), `cdnjs.cloudflare.com` (cropperjs 1.6.1)

**Maps:**
- Google Maps short links (`maps.app.goo.gl`) stored as venue URLs (`Venue`), no API calls

## Data Storage

**Databases:**
- PostgreSQL 18 (`postgres:18-alpine`)
  - Connection: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` (default `db`), `DB_PORT`, `DB_CONN_MAX_AGE`, `DB_CONN_HEALTH_CHECKS`, `DB_STATEMENT_TIMEOUT`
  - Client: Django ORM via `psycopg2-binary` (`config/settings.py`)

**File Storage:**
- Local filesystem only: `FileSystemStorage` for media (`/app/media`, host `/opt/videosvoley/media`); `ForgivingManifestStaticFilesStorage` for static (`ilovevoley/core/storage.py`)
- Protected media served via nginx X-Accel-Redirect (`PROTECTED_MEDIA_USE_X_ACCEL`, `ilovevoley/core/protected_media.py`)

**Caching:**
- Redis 8 (`redis:8-alpine`): DB0 Celery broker (`REDIS_URL`), DB1 Celery results (`REDIS_RESULT_URL`), DB2 Django cache and rate-limit store (`REDIS_CACHE_URL`)

## Authentication & Identity

**Auth Provider:**
- Custom `User` model (`ilovevoley/users/models.py`) + django-allauth
  - Google OAuth only identifies the user; `SOCIALACCOUNT_STORE_TOKENS = False`, basic scopes only
  - Adapter: `ilovevoley/users/adapters.py` (`CustomSocialAccountAdapter`)
  - Email verification optional; social email auto-connect to verified local account
  - Per-club `Membership` roles (`admin`, `manager`, `member`); moderation panel `/core/moderacion/`
  - Multi-tenant by subdomain: `TenantMiddleware` (`ilovevoley/core/middleware.py`, `ilovevoley/core/tenancy.py`); `TENANT_BASE_DOMAIN`
- Docs: `ilovevoley/docs/AUTENTICACION.md`, `ilovevoley/docs/MULTI_TENANT.md`

**Web Push:**
- VAPID (RFC 8292) via `pywebpush` in `ilovevoley/users/webpush.py`; endpoints restricted to push-service hosts (e.g. `fcm.googleapis.com`)
- Auth: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS_SUB`

**Calendar:**
- ICS feed per user (`calendar_token`), not Google Calendar API

## Monitoring & Observability

**Error Tracking:**
- Sentry (`sentry-sdk[django]`, Django + Celery integrations, beat monitors) configured in `config/sentry.py`; disabled when `DEBUG` or no `SENTRY_DSN`
  - Env: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE` (from `GIT_SHA`), `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`, `SENTRY_MONITOR_BEAT_TASKS`; `send_default_pii=False`

**Logs:**
- Python logging (`config/logging_production.py`); gunicorn access log to stdout; nginx combined access log with bot filtering (`nginx.conf`); health endpoint `healthz`
- Technical alert emails: `TECHNICAL_ALERT_EMAILS`

## CI/CD & Deployment

**Hosting:**
- Self-hosted Docker Compose server behind nginx

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci-cd.yml`: Gitleaks, `pip-audit`, Bandit, `manage.py check` (+ `--deploy`), `makemigrations --check`, `compilemessages`, `pytest --create-db -n auto` against a Postgres 18 service; on push to `main`, deploy via SSH (`appleboy/ssh-action`) running `deploy.sh`
- Dependabot for uv updates; pre-commit (`.pre-commit-config.yaml`) compiles Tailwind and syncs `uv.lock`

## Environment Configuration

**Required env vars:**
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_PASSWORD` (prod), `DB_*`, `REDIS_*`, `TENANT_BASE_DOMAIN`, `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`, `VAPID_*`, `SENTRY_DSN`, `GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_API_KEY`
- Email: SMTP (default `smtp.gmail.com:587` TLS), `DEFAULT_FROM_EMAIL`, `NOTIFICATION_EMAIL_ENABLED`, `ADMIN_EMAIL_LIST`, `EMAIL_NOTIFY_*` toggles (`ilovevoley/core/email_utils.py`)

**Secrets location:**
- `.env` file on server (compose `env_file`), Google service-account JSON file mounted read-only, GitHub Actions secrets (`SSH_HOST`, `SSH_USER`, `SSH_KEY`); contents not inspected

## Webhooks & Callbacks

**Incoming:**
- Google OAuth callback via allauth (`/accounts/google/login/callback/`)
- `healthz` health check (SSL-redirect exempt)
- No third-party webhooks detected

**Outgoing:**
- Web Push to browser push services (FCM etc.)
- SMTP email notifications
- Gemini and Vision API calls; federation scraping HTTP requests

---

*Integration audit: 2026-10-22*
