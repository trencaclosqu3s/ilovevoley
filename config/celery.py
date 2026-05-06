import os
from celery import Celery
import django
from django.apps import apps as django_apps

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('videosvoley')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Exclude RAG app — its tasks use PyTorch/ChromaDB which are not fork-safe and cause
# the worker to freeze indefinitely (blocks all scraping tasks).
EXCLUDED_APPS = ['videosvoley.rag']
app.autodiscover_tasks(
    lambda: [ac.name for ac in django_apps.get_app_configs() if ac.name not in EXCLUDED_APPS]
)

# Force Django setup and import all tasks
django.setup()

try:
    from videosvoley.videos.tasks import *
except ImportError as e:
    print(f"Warning: Could not import video tasks: {e}")

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
