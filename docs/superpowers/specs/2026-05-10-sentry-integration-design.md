# Sentry Integration Design

**Date:** 2026-05-10  
**Status:** Approved

## Context

The project runs Django (gunicorn, 3 workers), Celery worker, and Celery beat — all as separate Docker services. Currently there is no centralized error tracking. The goal is to capture unhandled exceptions and basic performance traces across all processes.

## Requirements

- Capture errors and 500s from Django views
- Capture task failures from Celery worker and beat
- Basic performance monitoring (HTTP traces + task traces) at 10% sample rate
- Only active in production (`DEBUG=False`)
- No PII (no IPs, no cookies)

## Approach

Single `sentry_sdk.init()` call in `settings.py`, conditioned on `not DEBUG and SENTRY_DSN`. Uses `DjangoIntegration` and `CeleryIntegration`. No changes to `celery.py` — Celery imports Django settings, which triggers the init automatically.

## Changes

### `requirements.txt`

Add:
```
sentry-sdk[django]==2.x
```

### `.env` (user adds manually)

```ini
SENTRY_DSN=https://...@sentry.io/...
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### `config/settings.py`

New block at the end of the file:

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

SENTRY_DSN = env_config('SENTRY_DSN', default='')

if not DEBUG and SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=env_config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        send_default_pii=False,
        environment='production',
    )
```

## Coverage

| Process | Errors | Traces |
|---|---|---|
| gunicorn (Django views) | ✓ | ✓ |
| celery worker (tasks) | ✓ | ✓ |
| celery beat | ✓ | — |

## Out of Scope

- Release tracking (git SHA tagging) — can be added later
- Staging environment — only `production` for now
- Custom error filtering / `before_send` — no specific PII concerns beyond `send_default_pii=False`
- Profiling — `profiles_sample_rate` not needed at this stage
