from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ilovevoley.core'
    
    def ready(self):
        # Import calendar tasks when app is ready to ensure Celery registration
        try:
            from . import tasks
        except ImportError:
            pass
        try:
            from . import checks
        except ImportError:
            pass