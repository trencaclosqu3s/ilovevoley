"""
Configuración de la app teams.
"""
from django.apps import AppConfig


class TeamsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.teams'
    verbose_name = 'Equipos y Clubs'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import videosvoley.teams.signals