"""
Signals para la app rosters.
Migrados desde videos.signals para la nueva app rosters.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Person, PlayerRole, StaffRole


@receiver(post_save, sender=Person)
def person_saved_handler(sender, instance, created, **kwargs):
    """
    Maneja la creación/actualización de personas
    """
    if created:
        print(f"Nueva persona creada: {instance.full_name}")
    else:
        print(f"Persona actualizada: {instance.full_name}")


@receiver(post_delete, sender=Person)
def person_deleted_handler(sender, instance, **kwargs):
    """
    Maneja la eliminación de personas
    """
    print(f"Persona eliminada: {instance.full_name}")


@receiver(post_save, sender=PlayerRole)
def player_role_saved_handler(sender, instance, created, **kwargs):
    """
    Maneja la creación/actualización de roles de jugador
    """
    if created:
        print(f"Nuevo rol de jugador creado: {instance.person.full_name} en {instance.team.name}")
        
        # Actualizar estadísticas del equipo si es necesario
        update_team_stats(instance.team)
    else:
        print(f"Rol de jugador actualizado: {instance.person.full_name} en {instance.team.name}")
        
        # Si cambió el equipo, actualizar estadísticas de ambos equipos
        if hasattr(instance, '_old_team_id'):
            old_team_id = instance._old_team_id
            if old_team_id and old_team_id != instance.team_id:
                try:
                    from videosvoley.teams.models import Team
                    old_team = Team.objects.get(id=old_team_id)
                    update_team_stats(old_team)
                except Team.DoesNotExist:
                    pass
        
        update_team_stats(instance.team)


@receiver(post_delete, sender=PlayerRole)
def player_role_deleted_handler(sender, instance, **kwargs):
    """
    Maneja la eliminación de roles de jugador
    """
    print(f"Rol de jugador eliminado: {instance.person.full_name} de {instance.team.name}")
    
    # Actualizar estadísticas del equipo
    update_team_stats(instance.team)


@receiver(post_save, sender=StaffRole)
def staff_role_saved_handler(sender, instance, created, **kwargs):
    """
    Maneja la creación/actualización de roles de staff
    """
    if created:
        print(f"Nuevo rol de staff creado: {instance.person.full_name} en {instance.team.name}")
        
        # Actualizar estadísticas del equipo si es necesario
        update_team_stats(instance.team)
    else:
        print(f"Rol de staff actualizado: {instance.person.full_name} en {instance.team.name}")
        
        # Si cambió el equipo, actualizar estadísticas de ambos equipos
        if hasattr(instance, '_old_team_id'):
            old_team_id = instance._old_team_id
            if old_team_id and old_team_id != instance.team_id:
                try:
                    from videosvoley.teams.models import Team
                    old_team = Team.objects.get(id=old_team_id)
                    update_team_stats(old_team)
                except Team.DoesNotExist:
                    pass
        
        update_team_stats(instance.team)


@receiver(post_delete, sender=StaffRole)
def staff_role_deleted_handler(sender, instance, **kwargs):
    """
    Maneja la eliminación de roles de staff
    """
    print(f"Rol de staff eliminado: {instance.person.full_name} de {instance.team.name}")
    
    # Actualizar estadísticas del equipo
    update_team_stats(instance.team)


def update_team_stats(team):
    """
    Actualiza las estadísticas de un equipo
    """
    try:
        # Contar jugadores activos del equipo
        active_players = team.player_roles.filter(is_active=True).count()
        
        # Contar staff activo del equipo
        active_staff = team.staff_roles.filter(is_active=True).count()
        
        print(f"Equipo {team.name}: {active_players} jugadores activos, {active_staff} staff activo")
        
    except Exception as e:
        print(f"Error actualizando estadísticas del equipo {team.name}: {e}")


# Hooks para trackear cambios en equipo de roles
@receiver(post_save, sender=PlayerRole)
def track_player_role_team_changes(sender, instance, **kwargs):
    """
    Trackea cambios en el equipo del rol de jugador
    """
    # Clean up any tracking attributes
    if hasattr(instance, '_old_team_id'):
        del instance._old_team_id


@receiver(post_save, sender=StaffRole)
def track_staff_role_team_changes(sender, instance, **kwargs):
    """
    Trackea cambios en el equipo del rol de staff
    """
    # Clean up any tracking attributes
    if hasattr(instance, '_old_team_id'):
        del instance._old_team_id