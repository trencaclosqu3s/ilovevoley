import json
from django.contrib import admin
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from unfold.admin import ModelAdmin


# Desregistrar el admin por defecto de django-celery-beat
try:
    admin.site.unregister(PeriodicTask)
except admin.sites.NotRegistered:
    pass

@admin.register(PeriodicTask)
class CustomPeriodicTaskAdmin(BasePeriodicTaskAdmin, ModelAdmin):
    """
    Admin personalizado para tareas periódicas de Celery.
    Hereda del admin original de django-celery-beat para mantener toda la funcionalidad.
    
    Permite configurar tareas de scraping automático y otras tareas periódicas.
    """
    
    # Añadir campos personalizados a la lista existente
    list_display = BasePeriodicTaskAdmin.list_display + ('total_run_count',)
    
    # Mantener los fieldsets del original pero agregar descripciones útiles
    def get_fieldsets(self, request, obj=None):
        """Personalizar fieldsets con ayuda contextual"""
        fieldsets = super().get_fieldsets(request, obj)
        
        # Modificar fieldsets para agregar descripciones
        custom_fieldsets = []
        for name, opts in fieldsets:
            new_opts = opts.copy()
            
            # Agregar descripciones útiles
            if name is None or name == 'Información Básica' or 'name' in opts.get('fields', []):
                if 'description' not in new_opts:
                    new_opts['description'] = (
                        '<strong>Tareas disponibles:</strong><br>'
                        '• scrape_all_leagues - Scrapea todas las ligas activas (equipos, partidos, clasificaciones)<br>'
                        '• scrape_league - Scrapea una liga específica<br>'
                        '• scrape_calendar - Scrapea el calendario de partidos programados<br>'
                        '• scrape_results - Scrapea los resultados de partidos jugados<br>'
                        '• scrape_clubs - Scrapea clubes y asocia equipos<br>'
                        '• scrape_teams - Scrapea solo equipos de una liga específica<br>'
                        '• handle_withdrawn_teams - Gestiona equipos retirados y marca partidos como retirados<br><br>'
                        'Selecciona la tarea del desplegable "Task (registered)".'
                    )
            
            if 'args' in opts.get('fields', []) or 'kwargs' in opts.get('fields', []):
                new_opts['description'] = (
                    '<strong>Ejemplos de argumentos (kwargs):</strong><br><br>'
                    '<strong>scrape_all_leagues:</strong><br>'
                    '<code>{"delay": 2.0, "category_filter": "senior", "round_number": 1}</code><br><br>'
                    '<strong>scrape_league:</strong><br>'
                    '<code>{"league_id": "12345", "round_number": 1}</code><br><br>'
                    '<strong>scrape_calendar:</strong><br>'
                    '<code>{"league_id": "12345", "delay": 2.0}</code> (league_id opcional)<br><br>'
                    '<strong>scrape_results:</strong><br>'
                    '<code>{"league_id": "12345", "round_number": 5, "delay": 2.0}</code> (todos opcionales)<br><br>'
                    '<strong>scrape_clubs:</strong><br>'
                    '<code>{"match_teams": true, "delay": 1.0}</code><br><br>'
                    '<strong>scrape_teams:</strong><br>'
                    '<code>{"league_id": "7950", "category_name": "Senior", "dry_run": false, "delay": 1.0}</code><br>'
                    '<strong>Ejemplos específicos:</strong><br>'
                    '• <code>{"league_id": "8123", "category_name": "Juvenil"}</code> - Scrapea equipos juveniles<br>'
                    '• <code>{"league_id": "9456", "category_name": "Senior", "dry_run": true}</code> - Test sin guardar<br>'
                    '• <code>{"league_id": "7890", "category_name": "Cadete", "delay": 2.0}</code> - Con delay<br>'
                    '<em>league_id: ID federación, category_name: categoría a asignar (ambos requeridos)</em><br><br>'
                    '<strong>handle_withdrawn_teams:</strong><br>'
                    '<code>{"league_id": "12345", "dry_run": false, "reactivate_teams": false}</code> (todos opcionales)<br><br>'
                    '<em>Nota: Los argumentos deben estar en formato JSON válido.</em>'
                )
            
            custom_fieldsets.append((name, new_opts))
        
        return custom_fieldsets
    
    # Mantener las acciones del original y agregar las nuestras
    def get_actions(self, request):
        """Mantener las acciones del admin original y agregar solo las nuestras"""
        actions = super().get_actions(request)
        
        # Eliminar acciones duplicadas de django-celery-beat si existen
        duplicated_actions = ['run_selected_tasks', 'run_tasks']
        for action in duplicated_actions:
            if action in actions:
                del actions[action]
        
        # Agregar nuestra acción personalizada con función wrapper
        def run_tasks_action(modeladmin, request, queryset):
            return modeladmin.run_tasks_now(request, queryset)
        
        actions['run_tasks_now'] = (
            run_tasks_action,
            'run_tasks_now',
            'Ejecutar tareas seleccionadas ahora'
        )
        return actions
    
    def run_tasks_now(self, request, queryset):
        """Ejecuta las tareas seleccionadas inmediatamente"""
        if not queryset:
            self.message_user(request, 'No se seleccionaron tareas.')
            return
        from ilovevoley.videos.tasks import (
            scrape_all_leagues_task, 
            scrape_league_task, 
            scrape_calendar_task,
            scrape_results_task,
            scrape_clubs_task,
            scrape_teams_task,
            handle_withdrawn_teams_task
        )
        
        count = 0
        for task in queryset:
            try:
                # Mapear nombres de tareas a funciones
                task_map = {
                    'scrape_all_leagues': scrape_all_leagues_task,
                    'scrape_league': scrape_league_task,
                    'scrape_calendar': scrape_calendar_task,
                    'scrape_results': scrape_results_task,
                    'scrape_clubs': scrape_clubs_task,
                    'scrape_teams': scrape_teams_task,
                    'handle_withdrawn_teams': handle_withdrawn_teams_task,
                }
                
                if task.task in task_map:
                    # Ejecutar tarea de forma asíncrona
                    import json
                    args = json.loads(task.args) if task.args else []
                    kwargs = json.loads(task.kwargs) if task.kwargs else {}
                    
                    task_map[task.task].apply_async(args=args, kwargs=kwargs)
                    count += 1
                else:
                    self.message_user(
                        request, 
                        f'Tarea "{task.task}" no reconocida para ejecución manual',
                        level='WARNING'
                    )
            except Exception as e:
                self.message_user(
                    request, 
                    f'Error ejecutando tarea "{task.name}": {e}',
                    level='ERROR'
                )
        
        if count > 0:
            self.message_user(request, f'{count} tarea(s) enviada(s) a la cola de ejecución.')


