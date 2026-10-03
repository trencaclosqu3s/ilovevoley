import os
from celery import Celery
import django

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('ilovevoley')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

# Force Django setup and import all tasks
django.setup()

try:
    from ilovevoley.videos.tasks import *  # noqa: F401,F403
    import ilovevoley.core.tasks  # noqa: F401
    import ilovevoley.content.tasks  # noqa: F401
    import ilovevoley.users.tasks  # noqa: F401
    import ilovevoley.competitions.tasks  # noqa: F401
except ImportError as e:
    print(f"Warning: Could not import tasks: {e}")

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
