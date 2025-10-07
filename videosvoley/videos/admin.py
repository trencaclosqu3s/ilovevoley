from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.conf import settings
from django.db.models import Count
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django_celery_beat.admin import PeriodicTaskForm
from .models import Video, Category, League, Team, Match, ScrapingEndpoint, Standing, Club, Image
from .forms import MatchAdminForm


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'leagues_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)
    
    def leagues_count(self, obj):
        """Muestra el número de ligas asociadas"""
        return obj.leagues.count()
    leagues_count.short_description = 'Ligas'
    
    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'match', 'created_by', 'created_at')
    list_filter = ('category', 'match__league', 'created_at')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('match',)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'federation_id', 'competition_type', 'season', 'is_active')
    list_filter = ('category', 'competition_type', 'is_active', 'season')
    search_fields = ('name', 'federation_id', 'category__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('category',)
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'category', 'competition_type', 'season', 'is_active')
        }),
        ('Configuración', {
            'fields': ('base_url',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
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


@admin.register(Club)
class ClubAdmin(admin.ModelAdmin):
    list_display = ('official_name', 'federation_id', 'president', 'province', 'teams_count', 'logo_preview')
    list_filter = ('province', 'created_at')
    search_fields = ('official_name', 'federation_id', 'president', 'email')
    readonly_fields = ('created_at', 'updated_at', 'logo_federation_url')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('federation_id', 'official_name')
        }),
        ('Contacto', {
            'fields': ('president', 'email', 'phone', 'address')
        }),
        ('Sede', {
            'fields': ('venue_name', 'venue_address', 'province')
        }),
        ('Redes Sociales', {
            'fields': ('website', 'instagram', 'facebook', 'twitter'),
            'classes': ('collapse',)
        }),
        ('Logo', {
            'fields': ('logo_url', 'logo_federation_url')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['sync_selected_clubs']
    
    def teams_count(self, obj):
        """Muestra el número de equipos asociados"""
        return obj.teams.count()
    teams_count.short_description = 'Equipos'
    
    def logo_preview(self, obj):
        """Muestra preview del logo"""
        if obj.logo_federation_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 3px;" />',
                obj.logo_federation_url
            )
        return '-'
    logo_preview.short_description = 'Logo'
    
    def sync_selected_clubs(self, request, queryset):
        """Acción para sincronizar datos de clubes seleccionados"""
        from django.core.management import call_command
        from io import StringIO
        
        out = StringIO()
        club_ids = [club.federation_id for club in queryset]
        
        try:
            # Aquí se podría implementar sync específico por club
            self.message_user(request, f'Iniciado sync para {len(club_ids)} club(s)')
        except Exception as e:
            self.message_user(request, f'Error durante sync: {e}', level='ERROR')
    
    sync_selected_clubs.short_description = "Sincronizar datos de clubes seleccionados"


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'club_name', 'sponsor_name', 'federation_id', 'logo_preview')
    list_filter = ('category', 'club', 'created_at')
    search_fields = ('name', 'federation_id', 'sponsor_name', 'club__official_name', 'category__name')
    readonly_fields = ('created_at', 'display_logo')
    autocomplete_fields = ('club', 'category')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'club', 'category')
        }),
        ('Patrocinio', {
            'fields': ('sponsor_name',),
            'description': 'Nombre completo del equipo incluyendo patrocinadores'
        }),
        ('Logo', {
            'fields': ('logo_url', 'display_logo'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['match_to_clubs']
    
    def club_name(self, obj):
        """Muestra el nombre del club asociado"""
        return obj.club.official_name if obj.club else '-'
    club_name.short_description = 'Club'
    
    def logo_preview(self, obj):
        """Muestra preview del logo del equipo o club"""
        logo_url = obj.display_logo
        if logo_url:
            return format_html(
                '<img src="{}" width="30" height="30" style="border-radius: 3px;" />',
                logo_url
            )
        return '-'
    logo_preview.short_description = 'Logo'
    
    def match_to_clubs(self, request, queryset):
        """Acción para hacer matching automático de equipos seleccionados"""
        from django.core.management import call_command
        from io import StringIO
        
        teams_without_club = queryset.filter(club__isnull=True)
        if not teams_without_club.exists():
            self.message_user(request, 'Todos los equipos seleccionados ya tienen club asignado')
            return
        
        try:
            out = StringIO()
            call_command('scrape_clubs', '--match-teams', '--verbose', stdout=out)
            
            # Contar equipos que ahora tienen club
            matched_count = 0
            for team in teams_without_club:
                team.refresh_from_db()
                if team.club:
                    matched_count += 1
            
            if matched_count > 0:
                self.message_user(request, f'Se asociaron {matched_count} equipo(s) con clubes')
            else:
                self.message_user(request, 'No se pudieron hacer matches automáticos')
                
        except Exception as e:
            self.message_user(request, f'Error durante matching: {e}', level='ERROR')
    
    match_to_clubs.short_description = "Hacer matching automático con clubes"


class ScrapingEndpointInline(admin.TabularInline):
    model = ScrapingEndpoint
    extra = 1
    fields = ('endpoint_type', 'url_pattern', 'parser_type', 'is_active')


# Agregar inline de imágenes a MatchAdmin
class ImageInline(admin.TabularInline):
    model = Image
    extra = 0
    readonly_fields = ('thumbnail_preview', 'status', 'uploaded_by', 'upload_date')
    fields = ('thumbnail_preview', 'title', 'status', 'uploaded_by', 'upload_date')
    
    def thumbnail_preview(self, obj):
        """Miniatura para inline"""
        if obj.image:
            return format_html(
                '<img src="{}" width="40" height="40" style="object-fit: cover; border-radius: 3px;" />',
                obj.image.url
            )
        return '-'
    thumbnail_preview.short_description = 'Img'
    
    def has_add_permission(self, request, obj=None):
        """No permitir agregar desde inline"""
        return False


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


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    form = MatchAdminForm
    list_display = ('home_team', 'away_team', 'match_date', 'venue', 'status', 'result_display', 'league_category')
    list_filter = ('status', 'league', 'league__category', 'match_date')
    search_fields = ('home_team__name', 'away_team__name', 'venue', 'city', 'league__name')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'match_date'
    inlines = [ImageInline]
    fieldsets = (
        ('Configuración de Filtrado', {
            'fields': ('filter_by_category',),
            'description': 'Controla qué equipos se muestran en los campos de selección'
        }),
        ('Partido', {
            'fields': ('league', 'home_team', 'away_team', 'match_date')
        }),
        ('Ubicación', {
            'fields': ('venue', 'city')
        }),
        ('Resultado', {
            'fields': ('status', 'home_score', 'away_score')
        }),
        ('Metadata', {
            'fields': ('round_number', 'federation_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    class Media:
        js = ('admin/js/match_admin.js',)
    
    def league_category(self, obj):
        """Muestra la categoría de la liga"""
        return obj.league.category.name if obj.league and obj.league.category else '-'
    league_category.short_description = 'Categoría'
    
    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete en VideoAdmin"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


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


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('thumbnail_preview', 'title', 'match', 'categories_display_admin', 'status', 'uploaded_by', 'upload_date', 'moderated_by')
    list_filter = ('status', 'categories', 'year', 'upload_date', 'match__league')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('upload_date', 'thumbnail_preview', 'vision_api_details', 'moderation_date')
    date_hierarchy = 'upload_date'
    actions = ['approve_images', 'reject_images', 'check_with_vision_api']
    filter_horizontal = ('categories',)
    
    fieldsets = (
        ('Imagen', {
            'fields': ('thumbnail_preview', 'image', 'title', 'description', 'image_type', 'tags')
        }),
        ('Asociación', {
            'fields': ('match', 'categories', 'year'),
            'description': 'Categorías y año se asignan automáticamente desde el partido, pero puedes modificarlas'
        }),
        ('Moderación', {
            'fields': ('status', 'moderated_by', 'moderation_date', 'moderation_notes')
        }),
        ('Google Vision API', {
            'fields': ('vision_api_checked', 'vision_api_safe', 'vision_api_details'),
            'classes': ('collapse',),
            'description': 'Información de verificación automática de contenido'
        }),
        ('Metadata', {
            'fields': ('uploaded_by', 'upload_date'),
            'classes': ('collapse',)
        })
    )
    
    def thumbnail_preview(self, obj):
        """Muestra miniatura de la imagen"""
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="80" style="object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return '-'
    thumbnail_preview.short_description = 'Preview'
    
    def categories_display_admin(self, obj):
        """Muestra las categorías de forma legible"""
        cats = obj.categories.all()
        if cats:
            return ', '.join([cat.name for cat in cats])
        return '-'
    categories_display_admin.short_description = 'Categorías'
    
    def get_queryset(self, request):
        """Optimizar consultas con select_related y prefetch_related"""
        return super().get_queryset(request).select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories')
    
    def approve_images(self, request, queryset):
        """Acción masiva para aprobar imágenes"""
        updated = queryset.filter(status='pending').update(
            status='approved',
            moderated_by=request.user,
            moderation_date=timezone.now(),
            moderation_notes='Aprobada masivamente desde admin'
        )
        
        if updated:
            self.message_user(request, f'{updated} imagen(es) aprobada(s) correctamente.')
        else:
            self.message_user(request, 'No hay imágenes pendientes para aprobar.')
    
    approve_images.short_description = "Aprobar imágenes seleccionadas"
    
    def reject_images(self, request, queryset):
        """Acción masiva para rechazar imágenes"""
        updated = queryset.filter(status='pending').update(
            status='rejected',
            moderated_by=request.user,
            moderation_date=timezone.now(),
            moderation_notes='Rechazada masivamente desde admin'
        )
        
        if updated:
            self.message_user(request, f'{updated} imagen(es) rechazada(s) correctamente.')
        else:
            self.message_user(request, 'No hay imágenes pendientes para rechazar.')
    
    reject_images.short_description = "Rechazar imágenes seleccionadas"
    
    def check_with_vision_api(self, request, queryset):
        """Acción para verificar imágenes con Google Vision API"""
        if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
            self.message_user(request, 'Google Vision API no está habilitada.', level='WARNING')
            return
        
        try:
            from .utils import check_image_with_vision_api
            checked_count = 0
            unsafe_count = 0
            
            for image in queryset:
                if not image.vision_api_checked:
                    try:
                        result = check_image_with_vision_api(image.image)
                        image.vision_api_checked = True
                        image.vision_api_safe = result.get('safe', True)
                        image.vision_api_details = result
                        
                        if not result.get('safe', True):
                            unsafe_count += 1
                            # Auto-rechazar si no es segura
                            image.status = 'rejected'
                            image.moderated_by = request.user
                            image.moderation_date = timezone.now()
                            image.moderation_notes = 'Auto-rechazada por Google Vision API'
                        
                        image.save()
                        checked_count += 1
                        
                    except Exception as e:
                        self.message_user(request, f'Error verificando {image.title}: {e}', level='ERROR')
            
            if checked_count > 0:
                self.message_user(request, f'{checked_count} imagen(es) verificada(s) con Vision API.')
                if unsafe_count > 0:
                    self.message_user(request, f'{unsafe_count} imagen(es) marcada(s) como insegura(s).', level='WARNING')
            
        except ImportError:
            self.message_user(request, 'Utilidad de Vision API no disponible.', level='ERROR')
    
    check_with_vision_api.short_description = "Verificar con Google Vision API"
    
    def save_model(self, request, obj, form, change):
        """Auto-asignar moderador en cambios de estado"""
        if change and 'status' in form.changed_data:
            if obj.status in ['approved', 'rejected'] and not obj.moderated_by:
                obj.moderated_by = request.user
                obj.moderation_date = timezone.now()
        
        super().save_model(request, obj, form, change)


# =============================================================================
# Configuración de Celery Beat (Tareas Periódicas)
# =============================================================================

# Desregistrar el admin por defecto de django-celery-beat
try:
    admin.site.unregister(PeriodicTask)
except admin.sites.NotRegistered:
    pass

@admin.register(PeriodicTask)
class CustomPeriodicTaskAdmin(admin.ModelAdmin):
    """
    Admin personalizado para tareas periódicas de Celery.
    
    Permite configurar tareas de scraping automático y otras tareas periódicas.
    """
    form = PeriodicTaskForm  # Usar el formulario de django-celery-beat para detectar tareas
    
    list_display = (
        'name', 
        'task', 
        'enabled', 
        'interval_display', 
        'crontab_display',
        'last_run_at',
        'total_run_count'
    )
    list_filter = ('enabled', 'task', 'last_run_at')
    search_fields = ('name', 'task', 'description')
    readonly_fields = ('last_run_at', 'total_run_count', 'date_changed')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'task', 'enabled', 'description'),
            'description': 'En "Task (registered)" puedes elegir de las tareas disponibles '
                          'o escribir el nombre completo de una tarea personalizada.'
        }),
        ('Programación', {
            'fields': ('interval', 'crontab', 'solar', 'clocked'),
            'description': 'Elige UNA forma de programación: Interval (cada X tiempo), '
                          'Crontab (horarios específicos), Solar, o Clocked (una sola vez).'
        }),
        ('Argumentos', {
            'fields': ('args', 'kwargs'),
            'classes': ('collapse',),
            'description': '<strong>Argumentos para las tareas de scraping:</strong><br><br>'
                          '<strong>scrape_all_leagues:</strong><br>'
                          '{"delay": 2.0, "category_filter": "senior", "round_number": 1}<br><br>'
                          '<strong>scrape_league:</strong><br>'
                          '{"league_id": "12345", "round_number": 1}<br><br>'
                          '<strong>scrape_clubs:</strong><br>'
                          '{"match_teams": true, "delay": 1.0}<br><br>'
                          '<em>Nota: Los argumentos deben estar en formato JSON válido.</em>'
        }),
        ('Configuración Avanzada', {
            'fields': ('queue', 'exchange', 'routing_key', 'priority', 'expires', 'expire_seconds'),
            'classes': ('collapse',)
        }),
        ('Límites', {
            'fields': ('one_off', 'start_time', 'last_run_at', 'total_run_count'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('date_changed',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['enable_tasks', 'disable_tasks', 'run_tasks_now']
    
    def interval_display(self, obj):
        """Muestra el intervalo de forma legible"""
        if obj.interval:
            return str(obj.interval)
        return '-'
    interval_display.short_description = 'Intervalo'
    
    def crontab_display(self, obj):
        """Muestra el crontab de forma legible"""
        if obj.crontab:
            return str(obj.crontab)
        return '-'
    crontab_display.short_description = 'Crontab'
    
    def enable_tasks(self, request, queryset):
        """Habilita las tareas seleccionadas"""
        updated = queryset.update(enabled=True)
        self.message_user(request, f'{updated} tarea(s) habilitada(s) correctamente.')
    enable_tasks.short_description = "Habilitar tareas seleccionadas"
    
    def disable_tasks(self, request, queryset):
        """Deshabilita las tareas seleccionadas"""
        updated = queryset.update(enabled=False)
        self.message_user(request, f'{updated} tarea(s) deshabilitada(s) correctamente.')
    disable_tasks.short_description = "Deshabilitar tareas seleccionadas"
    
    def run_tasks_now(self, request, queryset):
        """Ejecuta las tareas seleccionadas inmediatamente"""
        from videosvoley.videos.tasks import scrape_all_leagues_task, scrape_league_task, scrape_clubs_task
        
        count = 0
        for task in queryset:
            try:
                # Mapear nombres de tareas a funciones
                task_map = {
                    'scrape_all_leagues': scrape_all_leagues_task,
                    'scrape_league': scrape_league_task,
                    'scrape_clubs': scrape_clubs_task,
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
    run_tasks_now.short_description = "Ejecutar tareas ahora"