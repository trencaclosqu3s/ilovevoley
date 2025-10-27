"""
Admin interface para la app competitions.
Migrado desde videos.admin para la nueva app competitions.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.conf import settings
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from .models import League, Match, Standing, ScrapingEndpoint
from .forms import MatchAdminForm, LeagueForm, StandingForm


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'federation_id', 'competition_type', 'season', 'match_format', 'visibility_type', 'is_our_team_related', 'is_historical', 'is_active', 'matches_count', 'created_at')
    list_filter = ('category', 'competition_type', 'match_format', 'visibility_type', 'is_our_team_related', 'is_historical', 'is_active', 'season')
    search_fields = ('name', 'federation_id', 'category__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('category',)
    list_editable = ('visibility_type', 'is_our_team_related', 'is_historical', 'is_active')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'category', 'competition_type', 'season')
        }),
        ('Formato de Partidos', {
            'fields': ('match_format', 'custom_max_sets', 'custom_sets_to_win'),
            'description': 'Configuración del formato de partidos y validación de resultados'
        }),
        ('Configuración de Visibilidad', {
            'fields': ('visibility_type', 'is_our_team_related', 'is_historical', 'is_active'),
            'description': 'Controla dónde y cómo se muestra la liga en la aplicación'
        }),
        ('Configuración Técnica', {
            'fields': ('base_url', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    def matches_count(self, obj):
        """Muestra el número de partidos asociados"""
        return obj.matches.count()
    matches_count.short_description = 'Partidos'
    
    def get_queryset(self, request):
        """Optimiza las consultas"""
        return super().get_queryset(request).prefetch_related('matches', 'category')
    
    def get_list_display(self, request):
        """Personaliza la lista según el usuario"""
        list_display = list(super().get_list_display(request))
        
        # Si es superusuario, mostrar todos los campos
        if request.user.is_superuser:
            return list_display
        
        # Para otros usuarios, ocultar algunos campos técnicos
        return [field for field in list_display if field not in ['base_url']]
    
    def get_list_filter(self, request):
        """Personaliza los filtros según el usuario"""
        list_filter = list(super().get_list_filter(request))
        
        # Agregar filtros específicos para gestión de ligas
        if request.user.is_superuser:
            list_filter.extend(['created_at'])
        
        return list_filter
    
    def get_actions(self, request):
        """Personaliza las acciones disponibles"""
        actions = super().get_actions(request)
        
        # Agregar acciones personalizadas para superusuarios
        if request.user.is_superuser:
            actions['mark_as_main'] = (
                self.mark_as_main,
                'mark_as_main',
                'Marcar como ligas principales'
            )
            actions['mark_as_reference'] = (
                self.mark_as_reference,
                'mark_as_reference',
                'Marcar como ligas de referencia'
            )
            actions['mark_as_historical'] = (
                self.mark_as_historical,
                'mark_as_historical',
                'Marcar como ligas históricas'
            )
            actions['mark_as_external'] = (
                self.mark_as_external,
                'mark_as_external',
                'Marcar como ligas externas'
            )
        
        return actions
    
    def mark_as_main(self, request, queryset):
        """Marca ligas como principales"""
        updated = queryset.update(
            visibility_type='main',
            is_our_team_related=True,
            is_historical=False
        )
        self.message_user(request, f'{updated} ligas marcadas como principales.')
    mark_as_main.short_description = "Marcar como ligas principales"
    
    def mark_as_reference(self, request, queryset):
        """Marca ligas como de referencia"""
        updated = queryset.update(
            visibility_type='reference',
            is_our_team_related=True,
            is_historical=False
        )
        self.message_user(request, f'{updated} ligas marcadas como de referencia.')
    mark_as_reference.short_description = "Marcar como ligas de referencia"
    
    def mark_as_historical(self, request, queryset):
        """Marca ligas como históricas"""
        updated = queryset.update(
            visibility_type='historical',
            is_historical=True,
            is_our_team_related=True
        )
        self.message_user(request, f'{updated} ligas marcadas como históricas.')
    mark_as_historical.short_description = "Marcar como ligas históricas"
    
    def mark_as_external(self, request, queryset):
        """Marca ligas como externas"""
        updated = queryset.update(
            visibility_type='external',
            is_our_team_related=False,
            is_historical=False
        )
        self.message_user(request, f'{updated} ligas marcadas como externas.')
    mark_as_external.short_description = "Marcar como ligas externas"
    
    actions = ['scrape_selected_leagues']
    
    def scrape_selected_leagues(self, request, queryset):
        """Acción personalizada para hacer scraping de ligas seleccionadas"""
        from videosvoley.videos.scraping import FederationScraper
        
        scraped_count = 0
        error_count = 0
        
        for league in queryset.filter(is_active=True):
            try:
                scraper = FederationScraper(league)
                scraper.scrape_all_endpoints()
                scraped_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(request, f'Error en {league.name}: {e}', level='ERROR')
        
        if scraped_count > 0:
            self.message_user(request, f'Scraping completado para {scraped_count} liga(s)')
        if error_count > 0:
            self.message_user(request, f'{error_count} liga(s) con errores', level='WARNING')
    
    scrape_selected_leagues.short_description = "Hacer scraping de ligas seleccionadas"


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    form = MatchAdminForm
    list_display = ('__str__', 'match_date', 'venue', 'status', 'result_display', 'league_category', 'match_type_display', 'teams_active_status', 'referee_display')
    list_filter = ('is_friendly', 'status', 'league', 'league__category', 'match_date', 'home_team__is_active', 'away_team__is_active', 'referee1', 'scorer')
    search_fields = ('home_team__name', 'away_team__name', 'venue', 'city', 'league__name', 'referee1', 'referee2', 'scorer', 'timekeeper', 'delegate', 'field_address')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'match_date'
    actions = ['mark_as_withdrawn', 'mark_as_scheduled']
    
    def get_queryset(self, request):
        """Usar all_objects en el admin para ver todos los partidos, incluyendo withdrawn"""
        return Match.all_objects.get_queryset()
    
    fieldsets = (
        ('Configuración de Filtrado', {
            'fields': ('filter_by_category',),
            'description': 'Controla qué equipos se muestran en los campos de selección'
        }),
        ('Tipo de Partido', {
            'fields': ('is_friendly',),
            'description': 'Marca como amistoso si se crea manualmente'
        }),
        ('Partido', {
            'fields': ('league', 'home_team', 'home_team_text', 'away_team', 'away_team_text', 'match_date'),
            'description': 'Para partidos amistosos, puedes usar campos de texto si el equipo no existe en BD'
        }),
        ('Ubicación', {
            'fields': ('venue', 'city', 'field_address')
        }),
        ('Resultado', {
            'fields': ('status', 'home_score', 'away_score')
        }),
        ('Personal Oficial', {
            'fields': ('referee1', 'referee2', 'scorer', 'timekeeper', 'delegate'),
            'classes': ('collapse',),
            'description': 'Personal técnico del partido (se llena automáticamente desde la federación)'
        }),
        ('Datos de la Federación', {
            'fields': ('federation_id', 'federation_club_local_id', 'federation_club_away_id', 'acta_html'),
            'classes': ('collapse',),
            'description': 'IDs y enlaces de la federación (se llenan automáticamente)'
        }),
        ('Metadata', {
            'fields': ('round_number', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    class Media:
        js = ('admin/js/match_admin.js',)
    
    def league_category(self, obj):
        """Muestra la categoría de la liga"""
        return obj.league.category.name if obj.league and obj.league.category else '-'
    league_category.short_description = 'Categoría'
    
    def match_type_display(self, obj):
        """Muestra el tipo de partido"""
        if obj.is_friendly:
            return '🏐 Amistoso'
        elif obj.federation_id:
            return '🏆 Oficial'
        return '❓ Otro'
    match_type_display.short_description = 'Tipo'
    
    def teams_active_status(self, obj):
        """Muestra el estado activo de los equipos"""
        # Para partidos amistosos con texto, no hay estado
        if not obj.home_team or not obj.away_team:
            return '-'
        
        home_status = "✓" if obj.home_team.is_active else "✗"
        away_status = "✓" if obj.away_team.is_active else "✗"
        
        if not obj.home_team.is_active or not obj.away_team.is_active:
            return format_html(
                '<span style="color: red;">{} / {}</span>',
                home_status, away_status
            )
        else:
            return format_html(
                '<span style="color: green;">{} / {}</span>',
                home_status, away_status
            )
    teams_active_status.short_description = 'Equipos Activos (L/V)'
    
    def referee_display(self, obj):
        """Muestra información de árbitros"""
        referees = []
        if obj.referee1:
            referees.append(f"1: {obj.referee1}")
        if obj.referee2:
            referees.append(f"2: {obj.referee2}")
        
        if referees:
            return format_html(
                '<div style="font-size: 11px; line-height: 1.2;">{}</div>',
                '<br>'.join(referees)
            )
        return '-'
    referee_display.short_description = 'Árbitros'
    
    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete en VideoAdmin"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct
    
    def mark_as_withdrawn(self, request, queryset):
        """Acción para marcar partidos como retirados"""
        updated = queryset.filter(status__in=['scheduled', 'postponed']).update(status='withdrawn')
        if updated:
            self.message_user(request, f'{updated} partido(s) marcado(s) como retirado(s).')
        else:
            self.message_user(request, 'No se pueden marcar como retirados partidos que ya están finalizados o en progreso.')
    mark_as_withdrawn.short_description = "Marcar como retirados (equipos fuera de liga)"
    
    def mark_as_scheduled(self, request, queryset):
        """Acción para reactivar partidos marcados como retirados"""
        updated = queryset.filter(status='withdrawn').update(status='scheduled')
        if updated:
            self.message_user(request, f'{updated} partido(s) reactivado(s) como programado(s).')
        else:
            self.message_user(request, 'No hay partidos retirados seleccionados para reactivar.')
    mark_as_scheduled.short_description = "Reactivar partidos retirados como programados"


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = ('position', 'team', 'league', 'total_points', 'played', 'won', 'lost')
    list_filter = ('league',)
    search_fields = ('team__name', 'league__name')
    readonly_fields = ('updated_at', 'set_difference', 'point_difference')
    ordering = ('league', 'position')
    fieldsets = (
        ('Posición', {
            'fields': ('league', 'team', 'position')
        }),
        ('Estadísticas Generales', {
            'fields': ('played', 'won', 'lost', 'total_points')
        }),
        ('Sets y Puntos', {
            'fields': ('sets_for', 'sets_against', 'points_for', 'points_against')
        }),
        ('Detalles Victorias/Derrotas', {
            'fields': ('wins_3_0', 'wins_3_1', 'wins_3_2', 'losses_2_3', 'losses_1_3', 'losses_0_3'),
            'classes': ('collapse',)
        }),
        ('Calculados', {
            'fields': ('set_difference', 'point_difference', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(ScrapingEndpoint)
class ScrapingEndpointAdmin(admin.ModelAdmin):
    list_display = ('league', 'endpoint_type', 'parser_type', 'is_active')
    list_filter = ('endpoint_type', 'parser_type', 'is_active')
    search_fields = ('league__name', 'url_pattern')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Configuración', {
            'fields': ('league', 'endpoint_type', 'parser_type', 'is_active')
        }),
        ('URL', {
            'fields': ('url_pattern',),
            'description': 'Usar {league_id}, {round}, etc. para parámetros dinámicos'
        }),
        ('Parámetros Adicionales', {
            'fields': ('extra_params',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


# =============================================================================
# Configuración de Celery Beat (Tareas Periódicas)
# =============================================================================

# Desregistrar el admin por defecto de django-celery-beat
try:
    admin.site.unregister(PeriodicTask)
except admin.sites.NotRegistered:
    pass

@admin.register(PeriodicTask)
class CustomPeriodicTaskAdmin(BasePeriodicTaskAdmin):
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
        from videosvoley.videos.tasks import (
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