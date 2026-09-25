# Sentry Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Sentry error tracking and basic performance monitoring (10% traces) to Django, Celery worker, and Celery beat — active only in production.

**Architecture:** A small `config/sentry.py` module exposes a `configure()` function with the init logic. Settings calls it at startup. Extracting the logic into a function (instead of bare module-level code) makes it unit-testable without module reload tricks.

**Tech Stack:** `sentry-sdk[django]` 2.x, `DjangoIntegration`, `CeleryIntegration`, `python-decouple`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `requirements.txt` | Add sentry-sdk dependency |
| Create | `config/sentry.py` | Testable `configure()` function |
| Modify | `config/settings.py` | Call `configure()` at startup |
| Create | `tests/__init__.py` | Make tests a package |
| Create | `tests/test_sentry.py` | Unit tests for configure() |

---

### Task 1: Add sentry-sdk dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the dependency**

  Open `requirements.txt` and append at the end:
  ```
  sentry-sdk[django]==2.29.1
  ```
  The `[django]` extra installs `DjangoIntegration`. `CeleryIntegration` is included in the base package.

- [ ] **Step 2: Verify the line is present**

  ```bash
  grep sentry requirements.txt
  ```
  Expected output:
  ```
  sentry-sdk[django]==2.29.1
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add requirements.txt
  git commit -m "deps: add sentry-sdk[django] for error tracking"
  ```

---

### Task 2: Write tests for Sentry configure() function

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_sentry.py`

- [ ] **Step 1: Create the tests package**

  Create an empty file `tests/__init__.py`.

- [ ] **Step 2: Write the failing tests**

  Create `tests/test_sentry.py`:

  ```python
  from unittest.mock import patch
  from sentry_sdk.integrations.django import DjangoIntegration
  from sentry_sdk.integrations.celery import CeleryIntegration


  def test_configure_does_not_init_when_debug_true():
      from config.sentry import configure
      with patch('sentry_sdk.init') as mock_init:
          configure(dsn='https://test@sentry.io/1', debug=True, traces_sample_rate=0.1)
          mock_init.assert_not_called()


  def test_configure_does_not_init_when_dsn_empty():
      from config.sentry import configure
      with patch('sentry_sdk.init') as mock_init:
          configure(dsn='', debug=False, traces_sample_rate=0.1)
          mock_init.assert_not_called()


  def test_configure_inits_in_production():
      from config.sentry import configure
      with patch('sentry_sdk.init') as mock_init:
          configure(dsn='https://test@sentry.io/1', debug=False, traces_sample_rate=0.1)
          mock_init.assert_called_once()
          kwargs = mock_init.call_args.kwargs
          assert kwargs['dsn'] == 'https://test@sentry.io/1'
          assert kwargs['traces_sample_rate'] == 0.1
          assert kwargs['send_default_pii'] is False
          assert kwargs['environment'] == 'production'


  def test_configure_includes_django_and_celery_integrations():
      from config.sentry import configure
      with patch('sentry_sdk.init') as mock_init:
          configure(dsn='https://test@sentry.io/1', debug=False, traces_sample_rate=0.1)
          integrations = mock_init.call_args.kwargs['integrations']
          integration_types = [type(i) for i in integrations]
          assert DjangoIntegration in integration_types
          assert CeleryIntegration in integration_types
  ```

- [ ] **Step 3: Run tests to confirm they fail**

  ```bash
  docker compose run --rm web python -m pytest tests/test_sentry.py -v
  ```
  Expected: `ModuleNotFoundError: No module named 'config.sentry'` (the module doesn't exist yet).

---

### Task 3: Implement config/sentry.py

**Files:**
- Create: `config/sentry.py`

- [ ] **Step 1: Create the module**

  Create `config/sentry.py`:

  ```python
  def configure(dsn, debug, traces_sample_rate):
      if debug or not dsn:
          return

      import sentry_sdk
      from sentry_sdk.integrations.django import DjangoIntegration
      from sentry_sdk.integrations.celery import CeleryIntegration

      sentry_sdk.init(
          dsn=dsn,
          integrations=[DjangoIntegration(), CeleryIntegration()],
          traces_sample_rate=traces_sample_rate,
          send_default_pii=False,
          environment='production',
      )
  ```

- [ ] **Step 2: Run tests to confirm they all pass**

  ```bash
  docker compose run --rm web python -m pytest tests/test_sentry.py -v
  ```
  Expected output:
  ```
  tests/test_sentry.py::test_configure_does_not_init_when_debug_true PASSED
  tests/test_sentry.py::test_configure_does_not_init_when_dsn_empty PASSED
  tests/test_sentry.py::test_configure_inits_in_production PASSED
  tests/test_sentry.py::test_configure_includes_django_and_celery_integrations PASSED
  4 passed
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add config/sentry.py tests/__init__.py tests/test_sentry.py
  git commit -m "feat(sentry): configure() function con Django y Celery integrations"
  ```

---

### Task 4: Wire configure() into settings.py

**Files:**
- Modify: `config/settings.py` (final lines)

- [ ] **Step 1: Add the Sentry block at the end of settings.py**

  Append at the very end of `config/settings.py`:

  ```python
  # Sentry error tracking and performance monitoring
  from config.sentry import configure as _configure_sentry
  _configure_sentry(
      dsn=env_config('SENTRY_DSN', default=''),
      debug=DEBUG,
      traces_sample_rate=env_config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
  )
  ```

- [ ] **Step 2: Verify tests still pass (no regression)**

  ```bash
  docker compose run --rm web python -m pytest tests/test_sentry.py -v
  ```
  Expected: `5 passed`

- [ ] **Step 3: Verify Django starts without errors**

  ```bash
  docker compose run --rm web python manage.py check
  ```
  Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 4: Commit**

  ```bash
  git add config/settings.py
  git commit -m "feat(sentry): inicializar Sentry desde settings.py en producción"
  ```

---

### Task 5: Rebuild Docker image and verify

**Files:** ninguno (solo operaciones de Docker)

- [ ] **Step 1: Asegúrate de tener el SENTRY_DSN en .env**

  El usuario ya ha añadido `SENTRY_DSN` al `.env`. Verifica que está presente:
  ```bash
  grep SENTRY .env
  ```
  Expected:
  ```
  SENTRY_DSN=https://...@sentry.io/...
  SENTRY_TRACES_SAMPLE_RATE=0.1
  ```

- [ ] **Step 2: Rebuild la imagen**

  ```bash
  docker compose build web
  ```
  Expected: build finaliza sin errores.

- [ ] **Step 3: Reiniciar todos los servicios**

  ```bash
  docker compose up -d
  ```

- [ ] **Step 4: Comprobar que sentry_sdk se importa en el worker**

  ```bash
  docker compose logs celery | grep -i sentry
  ```
  Si Sentry está activo, el SDK loguea en inicio. Si no hay líneas, es normal en modo silencioso — el SDK no loguea por defecto.

- [ ] **Step 5: Enviar un error de prueba para confirmar recepción en Sentry**

  ```bash
  docker compose run --rm web python manage.py shell -c "
  import sentry_sdk
  print('initialized:', sentry_sdk.is_initialized())
  sentry_sdk.capture_message('Test desde videosvoley', level='error')
  print('Mensaje enviado a Sentry')
  "
  ```
  Si `DEBUG=False` y el DSN es correcto, verás el evento en el dashboard de Sentry en ~30 segundos.

- [ ] **Step 6: Commit final (si queda algo sin commitear)**

  ```bash
  git status
  ```
  Debe estar limpio. Si no:
  ```bash
  git add -u && git commit -m "chore: limpieza post-integración Sentry"
  ```
