from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Organization


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
