from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ilovevoley.users'

    def ready(self):
        import ilovevoley.users.signals
