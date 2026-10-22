# Testing Patterns

**Analysis Date:** 2026-10-22

## Test Framework

**Runner:**
- pytest 9.1.1 + pytest-django 4.14.0 + pytest-xdist 3.8.0 (`pyproject.toml` dev group)
- Config: `pytest.ini` (`DJANGO_SETTINGS_MODULE = config.settings_test`, `python_files = test_*.py`, `testpaths = ilovevoley`, `addopts = --strict-markers`)

**Assertion Library:** Django `unittest` assertions (`self.assertEqual`, `assertIsNone`, ...). Almost all tests are classes; only ~13 files import `pytest`, and no `conftest.py` exists.

**Run Commands:**
```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -n auto   # full suite
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --reuse-db -n auto    # faster local iteration
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db --tb=short ilovevoley/rosters/tests/test_link_requests.py   # single file
```
- `--create-db` is mandatory in CI and whenever migrations change.
- Coverage: no tool configured, no threshold enforced.
- CI: `.github/workflows/ci-cd.yml` runs `pytest --create-db -n auto -v` against Postgres 18 service, plus bandit and pip-audit.

## Test File Organization

**Location:** separate `tests/` package per app, with `__init__.py`: `ilovevoley/<app>/tests/`.

**Naming:** `test_<topic>.py` (`test_models.py`, `test_views.py`, `test_forms.py`, `test_admin.py`, `test_templatetags.py`, `test_utils.py`) plus feature files named after the capability (`test_weekend.py`, `test_link_requests.py`, `test_callup_parser.py`, `test_match_reminder_push.py`, `test_scrape_*_command.py`).

**Structure:**
```
ilovevoley/<app>/tests/
├── __init__.py
├── test_models.py
├── test_views.py
└── test_<feature>.py
```
Apps with tests: `competitions` (largest), `content`, `core`, `rosters`, `users`, `teams`. ~123 test files total.

## Test Structure

**Suite Organization:** `django.test.TestCase` (~249 classes), `SimpleTestCase` for DB-free logic (~42). Shared setup via base classes (`PlayerCardTestBase` in `ilovevoley/rosters/tests/test_player_card.py`, `WrappedTestBase`, `NarrativeTestBase`) or mixins (`RoundFixtureMixin`).

```python
@override_settings(ALLOWED_HOSTS=[HOST_A, HOST_B, 'localhost'])
class PersonLinkRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org_a = Organization.objects.create(slug='club-a', name='Club A', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org_a, is_approved=True)

    def _request_link(self, host=HOST_A, **overrides):   # helper builds request
        return self.client.post(reverse('rosters:person_link_request'), data, HTTP_HOST=host)

    def test_solicitar_mi_ficha_crea_solicitud_pendiente_sin_vincular(self):
        self.client.force_login(self.user)
        ...
```

**Patterns:**
- Setup: `setUp` creating objects with the ORM directly (`Model.objects.create(...)`); no factory library, no fixtures files.
- Multi-tenant tests use `HTTP_HOST='club-a.ilovevoley.es'` with `override_settings(ALLOWED_HOSTS=...)`; clear `cache` in `setUp` (LocMem cache).
- Login with `self.client.force_login(user)`.
- Test names are descriptive Spanish sentences (`test_aprobar_mi_ficha_fija_el_usuario`) or English snake_case.
- A comment starting `# Justificación:` in a test states which product decision it protects (see `ilovevoley/competitions/tests/test_weekend.py`). Module docstrings state scope and what is deliberately not tested.
- Assert persistent effects (refresh_from_db, DB state), not only `status_code`.
- Dates: build explicit tz-aware datetimes (`ZoneInfo('Europe/Madrid')`) rather than a freeze library.

## Mocking

**Framework:** `unittest.mock` (`mock.patch`, `patch`, decorator form `@mock.patch(...)`), no extra libs.

**Patterns:**
```python
with mock.patch('ilovevoley.rosters.tasks.notify_web_push_organization_task.delay') as push, \
        mock.patch('ilovevoley.rosters.tasks.send_notification_email') as email:
    ...
with patch('ilovevoley.core.moderation_views.TOKEN_MAX_AGE', -1):
```
- Patch where the name is used (the consumer module path), including `.delay` of Celery tasks.

**What to Mock:** external services (Google Vision, web push, email senders, federation HTTP clients, PNG renderers such as `render_player_card`), narrative/LLM calls, module constants like token ages.

**What NOT to Mock:** the ORM, Django views/forms, the unit under test. Do not mock so much that only the mock is verified.

## Fixtures and Factories

**Test Data:** inline helpers and module constants (e.g. `TINY_GIF` bytes + `SimpleUploadedFile` in `ilovevoley/content/tests/test_tasks.py`); `_png()` helpers; per-class `setUp`.

**Settings overrides:** `config/settings_test.py` sets LocMem cache, `CELERY_TASK_ALWAYS_EAGER=True`, `CELERY_TASK_EAGER_PROPAGATES=True`, MD5 password hasher, fake VAPID keys. Per-test `@override_settings(...)` for feature flags (`GOOGLE_VISION_ENABLED`, `NOTIFICATION_EMAIL_ENABLED`); email asserted via `django.core.mail.outbox` with the locmem backend.

**Location:** no shared fixtures; reuse via base classes inside the same test module.

## Coverage

**Requirements:** None enforced; coverage is explicitly not a reason to write a test.

## Test Value Rules (mandatory, `docs/ai-guidelines/testing-guidelines.md`)

Before creating or modifying a test, justify it (in conversation and commit/PR message). A test exists only if it protects a product decision:
- Must exist: business rule, edge case that failed or would be costly, non-trivial data transformation (parsing, normalization, dedupe), persistent-effect flow, critical error handling (rollback, idempotency), ambiguous decision, integration between own components.
- Must not exist: framework behavior, bare `status_code` checks, decorative HTML/CSS, duplicates, over-mocked tests, trivial getters, generic `LoginRequiredMixin` checks, environment-config pinning, and **data-migration tests** (no `test_migrations.py`; never test `reverse()`).
- Always test: custom model methods, validation beyond Django, permissions, multi-tenant isolation/scoping, state transitions, complex managers/QuerySets. Skip: basic CRUD, simple `list_display`.
- Admin: test only custom methods, complex `get_queryset()`, custom actions, `save_model()`.
- Prefer lowest level that keeps the contract: pure functions directly, `RequestFactory` for a single view, `client` when routing/auth/middleware/messages matter.

## Test Types

**Unit Tests:** pure services and parsers (`test_callup_parser.py`, `test_weekend.py`, `test_season_utils.py`), `SimpleTestCase` where no DB.

**Integration Tests:** view/client tests with tenants, Celery tasks run eagerly, management commands (`test_scrape_*_command.py`), cross-tenant access (`ilovevoley/core/tests/test_cross_tenant_access.py`), security headers/CSP (`test_security_headers.py`, `test_csp_templates.py`), URL reverse sweep (`test_url_reverse_sweep.py`).

**E2E Tests:** Not used.

## Common Patterns

**Async/Celery Testing:** run eagerly via settings (`CELERY_TASK_ALWAYS_EAGER`), then assert outcomes; patch `.delay` when only the dispatch matters.
```python
@mock.patch('ilovevoley.rosters.tasks.generate_season_wrappeds_task.delay')
def test_...(self, delay): ...
```

**Error Testing:** assert no side effects after rejection (e.g. no `PersonLinkRequest` created, `person.user_id` stays `None`); idempotency checked by repeating the call and counting rows.

**Query counts:** `assertNumQueries` is not used.

**Test DB:** Postgres; always pass `--create-db` after migration changes.

---

*Testing analysis: 2026-10-22*
