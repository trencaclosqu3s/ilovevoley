"""
Signals para la app teams.
Migrados desde videos.signals para la nueva app teams.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Team, Club


@receiver(post_save, sender=Team)
def team_saved_handler(sender, instance, created, **kwargs):
    """
    Maneja la creación/actualización de equipos
    """
    if created:
        print(f"Nuevo equipo creado: {instance.name} ({instance.category.name if instance.category else 'Sin categoría'})")
        
        # Si el equipo tiene club, actualizar estadísticas del club
        if instance.club:
            update_club_stats(instance.club)
    else:
        print(f"Equipo actualizado: {instance.name}")
        
        # Si cambió el club, actualizar estadísticas de ambos clubs
        if hasattr(instance, '_old_club_id'):
            old_club_id = instance._old_club_id
            if old_club_id and old_club_id != instance.club_id:
                try:
                    old_club = Club.objects.get(id=old_club_id)
                    update_club_stats(old_club)
                except Club.DoesNotExist:
                    pass
        
        if instance.club:
            update_club_stats(instance.club)


@receiver(post_delete, sender=Team)
def team_deleted_handler(sender, instance, **kwargs):
    """
    Maneja la eliminación de equipos
    """
    print(f"Equipo eliminado: {instance.name}")
    
    # Actualizar estadísticas del club si tenía uno
    if instance.club:
        update_club_stats(instance.club)


@receiver(post_save, sender=Club)
def club_saved_handler(sender, instance, created, **kwargs):
    """
    Maneja la creación/actualización de clubs
    """
    if created:
        print(f"Nuevo club creado: {instance.official_name}")
    else:
        print(f"Club actualizado: {instance.official_name}")


@receiver(post_delete, sender=Club)
def club_deleted_handler(sender, instance, **kwargs):
    """
    Maneja la eliminación de clubs
    """
    print(f"Club eliminado: {instance.official_name}")


def update_club_stats(club):
    """
    Actualiza las estadísticas de un club
    """
    try:
        # Contar equipos activos del club
        active_teams = club.teams.filter(is_active=True).count()
        
        # Contar jugadores totales del club
        total_players = 0
        for team in club.teams.filter(is_active=True):
            total_players += team.player_roles.count()
        
        # Contar staff total del club
        total_staff = 0
        for team in club.teams.filter(is_active=True):
            total_staff += team.staff_roles.count()
        
        print(f"Club {club.official_name}: {active_teams} equipos, {total_players} jugadores, {total_staff} staff")
        
    except Exception as e:
        print(f"Error actualizando estadísticas del club {club.official_name}: {e}")


# Hook para trackear cambios en club de equipo
@receiver(post_save, sender=Team)
def track_team_club_changes(sender, instance, **kwargs):
    """
    Trackea cambios en el club del equipo
    """
    # Clean up any tracking attributes
    if hasattr(instance, '_old_club_id'):
        del instance._old_club_id