from django.contrib import admin
from django.db import transaction
from django.db.models import Count, Q
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from ilovevoley.teams.models import Team
from ilovevoley.teams.services import MATCH_THRESHOLD, find_best_club
from .models import Category, Organization, Season


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['slug', 'name', 'club', 'club_teams_count', 'instagram_url', 'default_home', 'is_active', 'created_at']
    list_filter = ['default_home', 'is_active']
    list_select_related = ['club']
    autocomplete_fields = ['club']
    search_fields = ['slug', 'name']
    readonly_fields = ['club_teams_count', 'club_names_status']
    fields = [
        'slug', 'name', 'logo', 'primary_color', 'secondary_color',
        'instagram_url', 'default_home', 'club', 'club_team_names', 'is_active',
        'club_teams_count', 'club_names_status',
    ]
    actions = ['assign_club_to_orphan_teams']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            club_active_teams=Count('club__teams', filter=Q(club__teams__is_active=True))
        )

    def club_teams_count(self, obj):
        """Número de equipos activos con la FK al club vinculado."""
        if not obj.club_id:
            return '-'
        count = getattr(obj, 'club_active_teams', None)
        if count is None:
            count = obj.club.teams.filter(is_active=True).count()
        return count
    club_teams_count.short_description = 'Equipos activos'

    def club_names_status(self, obj):
        """Avisa si club_team_names no casa con ningún equipo del club."""
        if not obj.club_id:
            return '-'
        names = [name for name in (obj.club_team_names or {}).values() if name]
        if not names:
            return format_html(
                '<span style="color:#b45309;">{}</span>',
                'Sin club_team_names',
            )
        q = Q()
        for name in names:
            q |= Q(name__icontains=name)
        if obj.club.teams.filter(q).exists():
            return format_html('<span style="color:#15803d;">{}</span>', 'OK')
        return format_html(
            '<span style="color:#b91c1c;">{}</span>',
            'club_team_names no casa con ningún equipo del club',
        )
    club_names_status.short_description = 'Consistencia de nombres'

    @admin.action(description='Asignar club a equipos huérfanos por coincidencia de nombre')
    def assign_club_to_orphan_teams(self, request, queryset):
        """Rellena Team.club en equipos sin club que casan con el club de la org."""
        total = 0
        with transaction.atomic():
            for org in queryset.filter(club__isnull=False).select_related('club'):
                matched = []
                for team in Team.objects.filter(club__isnull=True):
                    match = find_best_club(team.name, [org.club])
                    if match and match[1] >= MATCH_THRESHOLD:
                        team.club = org.club
                        matched.append(team)
                if matched:
                    Team.objects.bulk_update(matched, ['club'])
                    total += len(matched)
                    self.message_user(
                        request,
                        f'{org.slug}: {len(matched)} equipo(s) asignado(s) a {org.club}.',
                    )
        if not total:
            self.message_user(request, 'No se encontraron equipos huérfanos por coincidencia de nombre.')


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
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


@admin.register(Season)
class SeasonAdmin(ModelAdmin):
    list_display = ('name', 'start_year', 'end_year', 'is_current', 'created_at')
    list_filter = ('is_current',)
    search_fields = ('name',)
    ordering = ('-start_year',)
    readonly_fields = ('start_year', 'end_year', 'created_at')
    actions = ('mark_as_current',)

    @admin.action(description='Marcar como temporada activa')
    def mark_as_current(self, request, queryset):
        season = queryset.order_by('-start_year').first()
        if not season:
            self.message_user(request, 'No se seleccionó ninguna temporada.', level='error')
            return
        season.is_current = True
        season.save()
        self.message_user(request, f'{season.name} marcada como temporada activa.')
