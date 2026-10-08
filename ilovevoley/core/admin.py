from django.contrib import admin
from django.db import transaction
from django.db.models import Count, Q
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from ilovevoley.teams.models import Club, Team
from ilovevoley.competitions.models import Match
from ilovevoley.teams.services import resolve_team_clubs
from .models import Category, Organization, Season


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['slug', 'name', 'club', 'club_teams_count', 'instagram_url', 'default_home', 'notify_match_changes', 'has_male_branch', 'has_female_branch', 'has_mixed_branch', 'is_active', 'created_at']
    list_filter = ['default_home', 'notify_match_changes', 'has_male_branch', 'has_female_branch', 'has_mixed_branch', 'is_active']
    list_select_related = ['club']
    autocomplete_fields = ['club']
    search_fields = ['slug', 'name']
    readonly_fields = ['club_teams_count', 'club_names_status']
    fields = [
        'slug', 'name', 'logo', 'primary_color', 'secondary_color', 'gradient_color',
        'instagram_url', 'default_home', 'club', 'club_team_names', 'is_active',
        'notify_match_changes', 'has_male_branch', 'has_female_branch',
        'has_mixed_branch', 'club_teams_count', 'club_names_status',
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
    club_teams_count.short_description = _('Equipos activos')

    def club_names_status(self, obj):
        """Avisa si club_team_names no casa con ningún equipo del club."""
        if not obj.club_id:
            return '-'
        names = [name for name in (obj.club_team_names or {}).values() if name]
        if not names:
            return format_html(
                '<span style="color:#b45309;">{}</span>',
                _('Sin club_team_names'),
            )
        q = Q()
        for name in names:
            q |= Q(name__icontains=name)
        if obj.club.teams.filter(q).exists():
            return format_html('<span style="color:#15803d;">{}</span>', 'OK')
        return format_html(
            '<span style="color:#b91c1c;">{}</span>',
            _('club_team_names no casa con ningún equipo del club'),
        )
    club_names_status.short_description = _('Consistencia de nombres')

    @admin.action(description=_('Asignar club a equipos huérfanos según sus partidos'))
    def assign_club_to_orphan_teams(self, request, queryset):
        """Rellena Team.club en equipos sin club cuyos partidos los sitúan en el club de la org."""
        total = 0
        team_clubs = resolve_team_clubs(Match, Club)
        with transaction.atomic():
            for org in queryset.filter(club__isnull=False).select_related('club'):
                team_ids = [team_id for team_id, club in team_clubs.items() if club.pk == org.club_id]
                count = Team.objects.filter(club__isnull=True, pk__in=team_ids).update(club=org.club)
                if count:
                    total += count
                    self.message_user(
                        request,
                        _('%(slug)s: %(count)s equipo(s) asignado(s) a %(club)s.') % {
                            'slug': org.slug,
                            'count': count,
                            'club': org.club,
                        },
                    )
        if not total:
            self.message_user(request, _('No se encontraron equipos huérfanos con partidos de ese club.'))


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'gender', 'is_active', 'leagues_count', 'created_at')
    list_filter = ('gender', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)

    def leagues_count(self, obj):
        """Muestra el número de ligas asociadas"""
        return obj.leagues.count()
    leagues_count.short_description = _('Ligas')

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

    @admin.action(description=_('Marcar como temporada activa'))
    def mark_as_current(self, request, queryset):
        season = queryset.order_by('-start_year').first()
        if not season:
            self.message_user(request, _('No se seleccionó ninguna temporada.'), level='error')
            return
        season.is_current = True
        season.save()
        self.message_user(request, _('%(name)s marcada como temporada activa.') % {'name': season.name})

    def changelist_view(self, request, extra_context=None):
        Season.objects.current()
        return super().changelist_view(request, extra_context=extra_context)
