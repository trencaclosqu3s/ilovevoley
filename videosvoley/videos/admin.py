"""
Admin interface para la app videos.
Los admin han sido migrados a las nuevas apps específicas.
Este archivo mantiene las referencias para compatibilidad hacia atrás.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.conf import settings
from django.db.models import Count
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin

# Importar modelos de las nuevas apps para compatibilidad
from videosvoley.content.models import Video, Category, Image
from videosvoley.competitions.models import League, Match, ScrapingEndpoint, Standing
from videosvoley.teams.models import Team, Club
from videosvoley.rosters.models import Person, PlayerRole, StaffRole
from videosvoley.videos.models import Player, Staff  # Modelos obsoletos

# Los forms han sido migrados a las nuevas apps
# Importar desde las nuevas apps para compatibilidad
from videosvoley.competitions.forms import MatchAdminForm


# =============================================================================
# ADMIN COMPATIBILIDAD - REDIRIGE A LAS NUEVAS APPS
# =============================================================================

# Los admin han sido migrados a las nuevas apps específicas.
# Este archivo mantiene las referencias para compatibilidad hacia atrás.

# Importar admin de las nuevas apps para mantener compatibilidad
from videosvoley.content.admin import (
    CategoryAdmin,
    VideoAdmin, 
    ImageAdmin
)

from videosvoley.competitions.admin import (
    LeagueAdmin,
    MatchAdmin,
    StandingAdmin,
    ScrapingEndpointAdmin,
    CustomPeriodicTaskAdmin
)

from videosvoley.teams.admin import (
    TeamAdmin,
    ClubAdmin
)

from videosvoley.rosters.admin import (
    PersonAdmin,
    PlayerRoleAdmin,
    StaffRoleAdmin
)

# Los admin de las nuevas apps ya están registrados en sus propias apps
# No necesitamos re-registrarlos aquí para evitar conflictos

# PeriodicTask ya está registrado en competitions/admin.py
# No necesitamos re-registrarlo aquí

# =============================================================================
# MODELOS OBSOLETOS - MANTENER PARA COMPATIBILIDAD
# =============================================================================

# Los modelos Player y Staff están obsoletos, usar Person + Roles
# Se mantienen aquí solo para compatibilidad hacia atrás
# 
# PROBLEMA ORIGINAL:
# - Un mismo niño jugando en dos equipos contaba como dos personas distintas
# - Una entrenadora de infantil y cadete contaba como dos staffs distintos
#
# SOLUCIÓN IMPLEMENTADA:
# - Sistema Person + PlayerRole/StaffRole permite múltiples roles por persona
# - Una persona puede ser jugador Y staff simultáneamente
# - Una persona puede tener roles en múltiples equipos

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    """Admin para modelo Player obsoleto - usar Person + PlayerRole"""
    list_display = ('__str__', 'team', 'position', 'is_active', 'created_at')
    list_filter = ('team', 'team__category', 'position', 'is_active', 'created_at')
    search_fields = ('first_name', 'last_name', 'jersey_number', 'team__name')
    readonly_fields = ('created_at', 'updated_at')
    # autocomplete_fields = ('team', 'user')  # Comentado temporalmente - problema de orden de carga de apps
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('team', 'team__category')
    
    def has_add_permission(self, request):
        """No permitir agregar nuevos Player - usar Person + PlayerRole"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Solo permitir ver - usar Person + PlayerRole para editar"""
        return False


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    """Admin para modelo Staff obsoleto - usar Person + StaffRole"""
    list_display = ('__str__', 'team', 'role', 'is_active', 'created_at')
    list_filter = ('team', 'team__category', 'role', 'is_active', 'created_at')
    search_fields = ('first_name', 'last_name', 'team__name', 'email', 'phone')
    readonly_fields = ('created_at', 'updated_at')
    # autocomplete_fields = ('team', 'user')  # Comentado temporalmente - problema de orden de carga de apps
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('team', 'team__category')
    
    def has_add_permission(self, request):
        """No permitir agregar nuevos Staff - usar Person + StaffRole"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Solo permitir ver - usar Person + StaffRole para editar"""
        return False