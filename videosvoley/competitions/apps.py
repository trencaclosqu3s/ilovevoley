"""
Configuración de la app competitions.
"""
from django.apps import AppConfig


class CompetitionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.competitions'
    verbose_name = 'Competiciones'
    
    def ready(self):
        """Importar signals cuando la app esté lista"""
        import videosvoley.competitions.signals