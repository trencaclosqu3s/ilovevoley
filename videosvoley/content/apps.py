"""
Configuración de la app content.
"""
from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.content'
    verbose_name = 'Contenido'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import videosvoley.content.signals