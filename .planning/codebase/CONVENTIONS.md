# Coding Conventions

**Analysis Date:** 2026-10-22

## Naming Patterns

**Files:**
- Python modules `snake_case.py`, named after the capability, not the layer: `ilovevoley/rosters/link_requests.py`, `ilovevoley/competitions/services/weekend.py`, `ilovevoley/users/onboarding.py`.
- Domain apps live under `ilovevoley/<app>/` with `models/` (package or `models.py`), `views.py`, `forms.py`, `tasks.py`, `urls.py`, `admin/` or `admin.py`, `services/` (competitions), `tests/`.
- Test files: `test_<topic>.py` in `<app>/tests/` (see TESTING.md).

**Functions:**
- `snake_case`; private helpers prefixed `_` (`_resolve_local_datetime`, `_follow_targets` in `ilovevoley/competitions/services/weekend.py`).
- Celery tasks end in `_task` and carry an explicit registered name: `send_match_reminders_2h_task` with `@shared_task(name='send_match_reminders_2h')` (`ilovevoley/competitions/tasks.py`).

**Variables / constants:**
- Module constants `UPPER_SNAKE` with a comment explaining the why (`UPCOMING_LIMIT`, `ENTRY_CACHE_TTL`, `MAX_PENDING_REQUESTS`).
- Sentinels: `_CACHE_MISSING = object()`.

**Types / classes:**
- `PascalCase`; enums as Django `TextChoices` nested in the model (`PersonLinkRequest.Status.PENDING`, `PersonLinkRequest.Kind.SELF`).

**Language rule (from user/global instructions):** code (apps, models, variables, fields, routes) in English; docstrings, comments, issue text and user-facing strings in Spanish. Test method names are frequently Spanish (`test_aprobar_mi_ficha_fija_el_usuario`).

## Code Style

**Formatting:**
- No formatter or linter configured (no ruff/black/flake8 in `pyproject.toml` or CI). Follow PEP 8, 4-space indentation, single quotes for strings, trailing commas in multi-line calls, line length roughly <= 100-110.
- Pre-commit (`.pre-commit-config.yaml`) only compiles Tailwind (`scripts/build_tailwind.py`, stages `ilovevoley/static/css/app.css`) and keeps `uv.lock` in sync.

**Security linting:**
- `bandit -r config ilovevoley -x '*/tests/*' -ll` and `pip-audit` run in `.github/workflows/ci-cd.yml`.

**Python:** 3.13 (`requires-python = ">=3.13,<3.14"`), Django pinned `6.0.8`. Modern typing (`datetime | None`) appears in services, but type hints are sparse and optional.

## Import Organization

**Order:**
1. Standard library (`calendar`, `logging`, `datetime`)
2. Third party (`requests`, `celery`)
3. Django (`django.conf`, `django.db`, `django.utils`)
4. Project absolute imports (`from ilovevoley.core.models import ...`)
5. Same-package relative imports occasionally (`from .models import Person` in `ilovevoley/rosters/link_requests.py`)

**Path Aliases:** none; always absolute `ilovevoley.<app>...` imports. Parenthesised multi-line imports with trailing comma for long lists. Function-local imports are used to dodge cycles or in tests.

## Error Handling

**Patterns:**
- Business rules live in service/helper modules, not views (`ilovevoley/rosters/link_requests.py` docstring states this); views stay thin.
- Atomic persistence via `transaction.atomic()` and `IntegrityError` catching for idempotency (`link_requests.py`).
- Form/validation failures raise `django.core.exceptions.ValidationError`; volleyball scores must pass `validate_volleyball_score(home_score, away_score, league)` before a match is finished.
- External API/scraper failures are caught and logged with `logger.warning`/`logger.error` and the work resumes next run (`ilovevoley/rosters/tasks.py`). Missing-object in tasks: warn and return (`notify_image_pending: image %s gone`).
- Sentry (`config/sentry.py`) captures unhandled errors in production.

## Logging

**Framework:** stdlib `logging`, module-level `logger = logging.getLogger(__name__)`.

**Patterns:**
- Only `logger.warning` / `logger.error` for real problems. Do not add `logger.info` in normal task flow; explain non-obvious branches with a comment instead.
- Never `print(`, `.debug(` or `console.log(` (blocked by pre-commit in related repos).
- Production log config in `config/logging_production.py`.

## Comments

**When to Comment:**
- Spanish comments explain the decision and its ceiling, with the issue number: `(#531)`, `(#522)`, `(#280)`. Reference issues in docstrings/comments for traceability.
- Never mention tooling/mode prefixes (e.g. `ponytail:`) in code comments.
- Module docstrings describe the rules owned by the module (`ilovevoley/rosters/link_requests.py`).

**Docstrings:** triple-quoted, Spanish, short summary sentence first, then rules (ventana, límites) when non-obvious.

## Function Design

**Size:** services are small, single-purpose functions with named constants for limits.

**Parameters:** explicit keyword-friendly args; request/user/organization passed in, not read from globals.

**Return Values:** `None` for "not found" lookups (`find_person`), querysets for filters, dicts/dataclass-like for summaries.

## Domain Rules to Follow (from `CLAUDE.md`)

- Seasons: `Season.objects.current()`; UI filter via `resolve_season_filter(request)`.
- Matches: `Match.objects` (excludes `withdrawn`) vs `Match.all_objects`.
- Tenancy: scope `Person` with `Person.objects.for_tenant`; roles via `PersonRoleTenantQuerySet`; middleware `TenantMiddleware` (`ilovevoley/core/middleware.py`, `ilovevoley/core/tenancy.py`).
- Celery tasks: always `name=`; never remove (PeriodicTask rows depend on it).
- i18n: user-visible strings wrapped with `gettext`/`gettext_lazy as _`; models use `gettext_lazy`, views `gettext`. Locales `es`, `ca` in `locale/<lang>/LC_MESSAGES/django.po`. Out-of-request messages use `ilovevoley.core.i18n`. In `<script>`, `{% trans %} as x` + `{{ x|escapejs }}`.
- New models/views go in their domain app, never in legacy `ilovevoley/videos`.
- Migrations: generate with `makemigrations`; never hand-edit existing ones; data backfills via `RunPython` migrations, not commands.
- Dependencies: edit `pyproject.toml` then `uv lock`; no `requirements.txt`.

## Module Design

**Exports:** no `__all__`; import by explicit module path.

**Barrel Files:** `__init__.py` mostly empty; `models/` and `admin/` packages exist in `competitions`, `rosters`.

---

*Convention analysis: 2026-10-22*
