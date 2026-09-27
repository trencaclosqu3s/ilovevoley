from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import MatchShareLink


@admin.register(MatchShareLink)
class MatchShareLinkAdmin(ModelAdmin):
    list_display = ('token', 'match', 'organization', 'created_by', 'created_at', 'expires_at', 'revoked_at')
    list_filter = ('organization', 'created_at')
    search_fields = ('match__home_team__name', 'match__away_team__name', 'token')
    readonly_fields = ('token', 'created_at')
    autocomplete_fields = ('match',)
    list_select_related = ('match__home_team', 'match__away_team', 'organization', 'created_by')
