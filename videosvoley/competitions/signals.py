"""
Signals para la app competitions.
Migrados desde videos.signals para la nueva app competitions.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Match


# Calendar sync signals for Match model
@receiver(post_save, sender=Match)
def match_saved_handler(sender, instance, created, **kwargs):
    """
    Trigger calendar sync when a match is created or updated.
    """
    if not getattr(settings, 'GOOGLE_CALENDAR_ENABLED', False):
        return
    
    # Only sync if the match has a category (required for filtering users)
    if not instance.league or not instance.league.category:
        return
    
    from videosvoley.core.tasks.calendar_tasks import sync_match_for_users
    
    if created:
        # New match - sync for all users who have this category
        sync_match_for_users.apply_async(args=[instance.id], countdown=10)
        print(f"New match {instance.id} created, queuing calendar sync for users")
    else:
        # Updated match - check if important fields changed
        if hasattr(instance, '_old_match_date') or hasattr(instance, '_old_venue') or hasattr(instance, '_old_status'):
            sync_match_for_users.apply_async(args=[instance.id], countdown=5)
            print(f"Match {instance.id} updated, queuing calendar sync for users")


@receiver(post_delete, sender=Match)
def match_deleted_handler(sender, instance, **kwargs):
    """
    Handle match deletion - this would require deleting calendar events.
    For now, we'll just log it since the calendar events will remain orphaned.
    """
    if not getattr(settings, 'GOOGLE_CALENDAR_ENABLED', False):
        return
        
    # TODO: Implement calendar event deletion for deleted matches
    # This would require storing event IDs in a separate model or
    # searching for events by match metadata
    print(f"Match {instance.id} deleted - calendar events may need manual cleanup")


# Add tracking for match changes
@receiver(post_save, sender=Match)
def track_match_changes(sender, instance, **kwargs):
    """
    Track changes in match fields that affect calendar events
    """
    # Clean up any tracking attributes
    for attr in ['_old_match_date', '_old_venue', '_old_status']:
        if hasattr(instance, attr):
            delattr(instance, attr)


@receiver(post_save, sender=Match)
def match_post_save(sender, instance, created, **kwargs):
    """
    Maneja la actualización automática de clasificaciones cuando se actualiza un partido
    """
    if not created and instance.is_finished and instance.home_score is not None and instance.away_score is not None:
        # Solo procesar si el partido está finalizado y tiene resultado
        try:
            # Actualizar clasificaciones de la liga
            from .utils import update_league_standings
            update_league_standings(instance.league)
        except Exception as e:
            print(f"Error actualizando clasificaciones para la liga {instance.league.id}: {e}")


@receiver(post_save, sender=Match)
def match_created_handler(sender, instance, created, **kwargs):
    """
    Maneja la creación de partidos amistosos
    """
    if created and instance.is_friendly:
        # Crear liga amistosa si no existe
        if not instance.league:
            from .models import League
            from videosvoley.content.models import Category
            
            # Buscar o crear categoría amistosa
            friendly_category, _ = Category.objects.get_or_create(
                name='Amistosos',
                defaults={
                    'description': 'Partidos amistosos',
                    'is_active': True
                }
            )
            
            # Crear liga amistosa
            friendly_league, _ = League.objects.get_or_create(
                name='Partidos Amistosos',
                defaults={
                    'competition_type': 'friendly',
                    'season': '2024-25',
                    'is_active': True,
                    'description': 'Partidos amistosos del club',
                    'category': friendly_category
                }
            )
            
            instance.league = friendly_league
            instance.save(update_fields=['league'])