"""
Celery tasks for Google Calendar synchronization.
"""
import logging
from typing import Optional, List

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings
from django.db import models

from videosvoley.core.services.calendar_sync import get_calendar_service
from videosvoley.videos.models import Match

User = get_user_model()
logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_user_calendar(self, user_id: int, force: bool = False):
    """
    Sync calendar for a specific user.
    
    Args:
        user_id: ID of the user to sync
        force: Force sync even if recently synced
    """
    try:
        user = User.objects.get(id=user_id)
        
        if not user.can_sync_calendar():
            logger.info(f"User {user.username} cannot sync calendar, skipping")
            return {'status': 'skipped', 'reason': 'cannot_sync'}
        
        # Check if recently synced (unless forced)
        if not force and user.calendar_last_sync:
            time_since_sync = timezone.now() - user.calendar_last_sync
            if time_since_sync.total_seconds() < 3600:  # 1 hour
                logger.info(f"User {user.username} synced recently, skipping")
                return {'status': 'skipped', 'reason': 'recently_synced'}
        
        calendar_service = get_calendar_service(user)
        if not calendar_service:
            logger.error(f"Could not get calendar service for user {user.username}")
            return {'status': 'error', 'reason': 'no_service'}
        
        # Test connection first
        if not calendar_service.test_connection():
            logger.error(f"Calendar connection test failed for user {user.username}")
            return {'status': 'error', 'reason': 'connection_failed'}
        
        # Perform sync
        stats = calendar_service.sync_user_matches(force=force)
        
        logger.info(f"Calendar sync completed for user {user.username}: {stats}")
        return {
            'status': 'success',
            'user_id': user_id,
            'username': user.username,
            'stats': stats
        }
        
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found")
        return {'status': 'error', 'reason': 'user_not_found'}
    
    except Exception as exc:
        logger.error(f"Error syncing calendar for user {user_id}: {exc}")
        
        # Retry for certain types of errors
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying calendar sync for user {user_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc)
        
        return {
            'status': 'error',
            'reason': 'exception',
            'error': str(exc),
            'user_id': user_id
        }


@shared_task(bind=True, max_retries=2)
def sync_match_for_users(self, match_id: int, user_ids: Optional[List[int]] = None):
    """
    Sync a specific match for users who have calendar sync enabled.
    
    Args:
        match_id: ID of the match to sync
        user_ids: Optional list of specific user IDs to sync. If None, sync for all eligible users.
    """
    try:
        match = Match.objects.select_related(
            'home_team', 'away_team', 'league__category'
        ).get(id=match_id)
        
        if not match.league or not match.league.category:
            logger.info(f"Match {match_id} has no category, skipping calendar sync")
            return {'status': 'skipped', 'reason': 'no_category'}
        
        # Get users who should sync this match
        if user_ids:
            users = User.objects.filter(
                id__in=user_ids,
                calendar_sync_enabled=True,
                preferred_categories=match.league.category
            )
        else:
            users = User.objects.filter(
                calendar_sync_enabled=True,
                preferred_categories=match.league.category
            )
        
        synced_users = []
        errors = []
        
        for user in users:
            try:
                if not user.has_google_calendar_permissions():
                    logger.info(f"User {user.username} lacks calendar permissions, skipping")
                    continue
                
                calendar_service = get_calendar_service(user)
                if not calendar_service:
                    logger.error(f"Could not get calendar service for user {user.username}")
                    errors.append({'user_id': user.id, 'error': 'no_service'})
                    continue
                
                # Find existing events for this match
                existing_events = calendar_service.find_events_by_match(match)
                
                if existing_events:
                    # Update existing event
                    event_id = existing_events[0].get('id')
                    if calendar_service.update_event(event_id, match):
                        synced_users.append({'user_id': user.id, 'action': 'updated'})
                    else:
                        errors.append({'user_id': user.id, 'error': 'update_failed'})
                        
                    # Clean up duplicates
                    for extra_event in existing_events[1:]:
                        calendar_service.delete_event(extra_event.get('id'))
                else:
                    # Create new event
                    event_id = calendar_service.create_event(match)
                    if event_id:
                        synced_users.append({'user_id': user.id, 'action': 'created'})
                    else:
                        errors.append({'user_id': user.id, 'error': 'create_failed'})
                        
            except Exception as e:
                logger.error(f"Error syncing match {match_id} for user {user.id}: {e}")
                errors.append({'user_id': user.id, 'error': str(e)})
        
        logger.info(f"Match {match_id} sync completed. Users synced: {len(synced_users)}, Errors: {len(errors)}")
        
        return {
            'status': 'completed',
            'match_id': match_id,
            'synced_users': synced_users,
            'errors': errors
        }
        
    except Match.DoesNotExist:
        logger.error(f"Match with ID {match_id} not found")
        return {'status': 'error', 'reason': 'match_not_found'}
    
    except Exception as exc:
        logger.error(f"Error syncing match {match_id}: {exc}")
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying match sync for {match_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc)
        
        return {
            'status': 'error',
            'reason': 'exception',
            'error': str(exc),
            'match_id': match_id
        }


@shared_task
def daily_calendar_sync():
    """
    Daily task to sync calendars for all users who have it enabled.
    Runs once per day to catch any missed updates.
    """
    if not settings.GOOGLE_CALENDAR_ENABLED:
        logger.info("Google Calendar sync is disabled, skipping daily sync")
        return {'status': 'disabled'}
    
    # Get users who have calendar sync enabled and haven't synced recently
    cutoff_time = timezone.now() - timezone.timedelta(hours=23)  # Allow some overlap
    users = User.objects.filter(
        calendar_sync_enabled=True,
        preferred_categories__isnull=False
    ).filter(
        models.Q(calendar_last_sync__isnull=True) |
        models.Q(calendar_last_sync__lt=cutoff_time)
    ).distinct()
    
    total_users = users.count()
    if total_users == 0:
        logger.info("No users need calendar sync")
        return {'status': 'no_users', 'total_users': 0}
    
    logger.info(f"Starting daily calendar sync for {total_users} users")
    
    # Queue individual sync tasks
    for user in users:
        sync_user_calendar.delay(user.id, force=False)
    
    return {
        'status': 'queued',
        'total_users': total_users,
        'message': f'Queued calendar sync for {total_users} users'
    }


@shared_task
def cleanup_calendar_events(user_id: int, days_old: int = 90):
    """
    Clean up old calendar events for a user.
    
    Args:
        user_id: ID of the user
        days_old: Remove events older than this many days
    """
    try:
        user = User.objects.get(id=user_id)
        
        if not user.can_sync_calendar():
            return {'status': 'skipped', 'reason': 'cannot_sync'}
        
        calendar_service = get_calendar_service(user)
        if not calendar_service:
            return {'status': 'error', 'reason': 'no_service'}
        
        # This would require implementing a cleanup method in the service
        # For now, just log that it was requested
        logger.info(f"Calendar cleanup requested for user {user.username} (events older than {days_old} days)")
        
        return {
            'status': 'completed',
            'user_id': user_id,
            'message': f'Cleanup logged for user {user.username}'
        }
        
    except User.DoesNotExist:
        return {'status': 'error', 'reason': 'user_not_found'}
    except Exception as e:
        logger.error(f"Error cleaning up calendar for user {user_id}: {e}")
        return {'status': 'error', 'reason': str(e)}


# Convenience function to sync calendar for a match immediately
def sync_match_immediately(match_id: int, user_ids: Optional[List[int]] = None):
    """
    Synchronously sync a match for users (non-Celery version for immediate use).
    Use this for urgent updates that can't wait for task queue.
    """
    return sync_match_for_users.apply(args=[match_id, user_ids]).get()