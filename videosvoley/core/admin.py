from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Category, Organization


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
