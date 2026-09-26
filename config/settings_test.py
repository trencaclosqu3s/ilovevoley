"""Settings for pytest/CI: LocMem cache so tests do not require Redis."""
from config.settings import *  # noqa: F403

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'ilovevoley-tests',
    }
}

# Run Celery tasks inline so tests do not need a broker/worker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
