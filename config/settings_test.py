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

# Fast password hasher for tests to avoid PBKDF2 iteration overhead
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Claves VAPID para testing hermético
VAPID_PUBLIC_KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckj0bMWq0Ww6a_82nWCQL67eSQVRWc'
VAPID_PRIVATE_KEY = 'test_vapid_private_key_pem_or_raw'
VAPID_CLAIMS_SUB = 'mailto:test@ilovevoley.es'
