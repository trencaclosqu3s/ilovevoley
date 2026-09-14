from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['slug', 'name', 'instagram_url', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['slug', 'name']
    fields = [
        'slug', 'name', 'logo', 'primary_color', 'secondary_color',
        'instagram_url', 'club_team_names', 'is_active',
    ]
