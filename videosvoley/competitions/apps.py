from django.apps import AppConfig


class CompetitionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.competitions'
    verbose_name = 'Competiciones'
    
    def ready(self):
        """Configuración cuando la app está lista"""
        # Importar signals si los hay
        try:
            import videosvoley.competitions.signals
        except ImportError:
            pass