from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Category, Organization, Season


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['slug', 'name', 'club', 'instagram_url', 'is_active', 'created_at']
    list_filter = ['is_active']
    list_select_related = ['club']
    autocomplete_fields = ['club']
    search_fields = ['slug', 'name']
    fields = [
        'slug', 'name', 'logo', 'primary_color', 'secondary_color',
        'instagram_url', 'club', 'club_team_names', 'is_active',
    ]


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
