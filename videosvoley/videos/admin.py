from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.conf import settings
from django.db.models import Count
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
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
    list_display = ('name', 'category', 'club_name', 'sponsor_name', 'federation_id', 'is_active', 'logo_preview')
    list_filter = ('is_active', 'category', 'club', 'created_at')
    search_fields = ('name', 'federation_id', 'sponsor_name', 'club__official_name', 'category__name')
    readonly_fields = ('created_at', 'display_logo')
    autocomplete_fields = ('club', 'category')
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'club', 'category', 'is_active')
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
    
    actions = ['match_to_clubs', 'activate_teams', 'deactivate_teams']
    
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
    
    def activate_teams(self, request, queryset):
        """Acción para activar equipos seleccionados"""
        updated = queryset.filter(is_active=False).update(is_active=True)
        if updated:
            self.message_user(request, f'{updated} equipo(s) activado(s) correctamente.')
        else:
            self.message_user(request, 'Todos los equipos seleccionados ya estaban activos.')
    activate_teams.short_description = "Activar equipos seleccionados"
    
    def deactivate_teams(self, request, queryset):
        """Acción para desactivar equipos seleccionados"""
        updated = queryset.filter(is_active=True).update(is_active=False)
        if updated:
            self.message_user(request, f'{updated} equipo(s) desactivado(s) correctamente.')
            self.message_user(request, 'Los partidos de estos equipos se marcarán como retirados en el próximo scraping.', level='WARNING')
        else:
            self.message_user(request, 'Todos los equipos seleccionados ya estaban inactivos.')
    deactivate_teams.short_description = "Desactivar equipos seleccionados"


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
    list_display = ('__str__', 'match_date', 'venue', 'status', 'result_display', 'league_category', 'match_type_display', 'teams_active_status')
    list_filter = ('is_friendly', 'status', 'league', 'league__category', 'match_date', 'home_team__is_active', 'away_team__is_active')
    search_fields = ('home_team__name', 'away_team__name', 'venue', 'city', 'league__name')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'match_date'
    inlines = [ImageInline]
    actions = ['mark_as_withdrawn', 'mark_as_scheduled']
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


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('thumbnail_preview', 'title', 'match', 'categories_display_admin', 'status', 'uploaded_by', 'upload_date', 'moderated_by', 'original_format', 'was_converted')
    list_filter = ('status', 'categories', 'year', 'upload_date', 'match__league', 'was_converted', 'original_format')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('upload_date', 'thumbnail_preview', 'vision_api_details', 'moderation_date', 'original_format', 'was_converted')
    date_hierarchy = 'upload_date'
    actions = ['approve_images', 'reject_images', 'check_with_vision_api']
    filter_horizontal = ('categories',)
    
    fieldsets = (
        ('Imagen', {
            'fields': ('thumbnail_preview', 'image', 'title', 'description', 'image_type', 'tags', 'original_format', 'was_converted')
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
                    '<strong>handle_withdrawn_teams:</strong><br>'
                    '<code>{"league_id": "12345", "dry_run": false, "reactivate_teams": false}</code> (todos opcionales)<br><br>'
                    '<em>Nota: Los argumentos deben estar en formato JSON válido.</em>'
                )
            
            custom_fieldsets.append((name, new_opts))
        
        return custom_fieldsets
    
    # Mantener las acciones del original y agregar las nuestras
    def get_actions(self, request):
        """Agregar acciones personalizadas a las existentes"""
        actions = super().get_actions(request)
        actions['run_tasks_now'] = (self.run_tasks_now, 'run_tasks_now', "Ejecutar tareas ahora")
        return actions
    
    def run_tasks_now(self, request, queryset):
        """Ejecuta las tareas seleccionadas inmediatamente"""
        from videosvoley.videos.tasks import (
            scrape_all_leagues_task, 
            scrape_league_task, 
            scrape_calendar_task,
            scrape_results_task,
            scrape_clubs_task,
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
    run_tasks_now.short_description = "Ejecutar tareas ahora"