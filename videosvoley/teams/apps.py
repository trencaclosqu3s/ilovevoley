from django.apps import AppConfig


class TeamsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.teams'
    verbose_name = 'Equipos y Clubs'
    
    def ready(self):
        """Configuración cuando la app está lista"""
        # Importar signals si los hay
        try:
            import videosvoley.teams.signals
        except ImportError:
            pass