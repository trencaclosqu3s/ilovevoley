from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from ilovevoley.competitions.models import FederationCallUp, FederationCircular, CallUpPlayer
from ilovevoley.competitions.services.callup_matcher import match_callup_player


class CallUpPlayerInline(TabularInline):
    model = CallUpPlayer
    fields = (
        'raw_first_name',
        'raw_last_name',
        'raw_club',
        'raw_birth_year',
        'organization',
        'person',
        'match_status',
        'match_score',
    )
    readonly_fields = ('match_score',)
    autocomplete_fields = ('organization', 'person')
    extra = 0


@admin.register(FederationCallUp)
class FederationCallUpAdmin(ModelAdmin):
    list_display = (
        'title',
        'circular_date',
        'callup_type',
        'modality',
        'category_name',
        'gender',
        'callup_number',
        'players_count_display',
        'source_url',
    )
    list_filter = ('season', 'callup_type', 'modality', 'category_name', 'gender')
    search_fields = ('title', 'source_url', 'raw_text')
    readonly_fields = ('pdf_sha256', 'created_at', 'updated_at')
    inlines = [CallUpPlayerInline]

    def players_count_display(self, obj):
        return obj.players.count()

    players_count_display.short_description = 'Jugadores'


@admin.register(CallUpPlayer)
class CallUpPlayerAdmin(ModelAdmin):
    list_display = (
        'raw_full_name',
        'raw_club',
        'raw_birth_year',
        'callup',
        'organization',
        'person',
        'match_status_badge',
        'match_score',
        'notification_sent',
    )
    list_filter = (
        'match_status',
        'notification_sent',
        'organization',
        'callup__season',
        'callup__modality',
    )
    search_fields = (
        'raw_first_name',
        'raw_last_name',
        'raw_club',
        'person__first_name',
        'person__last_name',
    )
    autocomplete_fields = ('organization', 'person', 'callup', 'reviewed_by')
    actions = ['confirm_matches', 'reject_matches', 're_evaluate_matches']

    def match_status_badge(self, obj):
        colors = {
            CallUpPlayer.STATUS_CONFIRMED: 'bg-green-100 text-green-800',
            CallUpPlayer.STATUS_SUSPECTED: 'bg-amber-100 text-amber-800',
            CallUpPlayer.STATUS_REJECTED: 'bg-red-100 text-red-800',
            CallUpPlayer.STATUS_UNMATCHED: 'bg-gray-100 text-gray-800',
        }
        color = colors.get(obj.match_status, 'bg-gray-100 text-gray-800')
        return format_html(
            '<span class="inline-flex px-2 py-0.5 rounded text-xs font-semibold {}">{}</span>',
            color,
            obj.get_match_status_display(),
        )

    match_status_badge.short_description = 'Estado'

    @action(description='Confirmar jugadores seleccionados como convocados')
    def confirm_matches(self, request, queryset):
        user = request.user if request and getattr(request, 'user', None) and request.user.is_authenticated else None
        count = queryset.update(
            match_status=CallUpPlayer.STATUS_CONFIRMED,
            reviewed_by=user,
            reviewed_at=timezone.now(),
        )
        if request:
            self.message_user(request, f"{count} convocatorias confirmadas.")

    @action(description='Descartar jugadores seleccionados')
    def reject_matches(self, request, queryset):
        user = request.user if request and getattr(request, 'user', None) and request.user.is_authenticated else None
        count = queryset.update(
            match_status=CallUpPlayer.STATUS_REJECTED,
            reviewed_by=user,
            reviewed_at=timezone.now(),
        )
        if request:
            self.message_user(request, f"{count} convocatorias descartadas.")

    @action(description='Reevaluar cruce antroponímico para los seleccionados')
    def re_evaluate_matches(self, request, queryset):
        updated = 0
        for player in queryset.select_related('callup__season'):
            data = {
                'club': player.raw_club,
                'first_name': player.raw_first_name,
                'last_name': player.raw_last_name,
                'birth_year': player.raw_birth_year,
            }
            res = match_callup_player(data, player.callup.season)
            player.organization = res.get('organization')
            player.person = res.get('person')
            player.match_status = res.get('match_status', 'unmatched')
            player.match_score = res.get('match_score', 0.0)
            player.match_notes = res.get('match_notes', '')
            player.save()
            updated += 1

        if request:
            self.message_user(request, f"{updated} jugadores reevaluados.")


@admin.register(FederationCircular)
class FederationCircularAdmin(ModelAdmin):
    list_display = ('title', 'tipo', 'circular_date', 'season', 'file_name')
    list_filter = ('tipo', 'season')
    search_fields = ('title',)
