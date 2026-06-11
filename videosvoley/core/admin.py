from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = ['slug', 'name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['slug', 'name']
