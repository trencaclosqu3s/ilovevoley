import os
from celery import Celery
import django

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('videosvoley')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Force Django setup and import all tasks
django.setup()
try:
    from videosvoley.core.tasks.calendar_tasks import *
except ImportError as e:
    print(f"Warning: Could not import calendar tasks: {e}")

try:
    from videosvoley.videos.tasks import *
except ImportError as e:
    print(f"Warning: Could not import video tasks: {e}")

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
