"""
Configuración de la app rosters.
"""
from django.apps import AppConfig


class RostersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.rosters'
    verbose_name = 'Plantillas y Personas'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import videosvoley.rosters.signals