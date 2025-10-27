from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.content'
    verbose_name = 'Contenido'
    
    def ready(self):
        """Configuración cuando la app está lista"""
        # Importar signals si los hay
        try:
            import videosvoley.content.signals
        except ImportError:
            pass