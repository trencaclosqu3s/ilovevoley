from django.apps import AppConfig


class RostersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.rosters'
    verbose_name = 'Plantillas y Roles'
    
    def ready(self):
        """Configuración cuando la app está lista"""
        # Importar signals si los hay
        try:
            import videosvoley.rosters.signals
        except ImportError:
            pass