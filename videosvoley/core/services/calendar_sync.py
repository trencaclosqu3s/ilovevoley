"""
Google Calendar synchronization service for VideosVoley matches.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from django.conf import settings
from django.utils import timezone
from allauth.socialaccount.models import SocialToken, SocialAccount

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from videosvoley.videos.models import Match

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Service for managing Google Calendar synchronization."""
    
    def __init__(self, user):
        self.user = user
        self.service = None
        self.calendar_id = user.google_calendar_id or 'primary'
        
    def _get_credentials(self) -> Optional[Credentials]:
        """Get Google credentials for the user."""
        try:
            google_account = self.user.socialaccount_set.filter(provider='google').first()
            if not google_account:
                logger.warning(f"No Google account found for user {self.user.username}")
                return None
            
            token = SocialToken.objects.filter(
                account=google_account,
                app__provider='google'
            ).first()
            
            if not token:
                logger.warning(f"No Google token found for user {self.user.username}")
                return None
            
            # Check if we have refresh token
            if not token.token_secret:
                logger.warning(f"No refresh token found for user {self.user.username}. User needs to reconnect with Calendar permissions.")
                # Auto-disable calendar sync to prevent spam
                self.user.calendar_sync_enabled = False
                self.user.save()
                return None
            
            # Get client credentials from SocialApp
            social_app = token.app
            
            # Create credentials object
            creds = Credentials(
                token=token.token,
                refresh_token=token.token_secret,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=social_app.client_id,
                client_secret=social_app.secret,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            # Refresh token if expired
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Update stored token
                    token.token = creds.token
                    if creds.expiry:
                        token.expires_at = creds.expiry
                    token.save()
                    logger.info(f"Successfully refreshed token for user {self.user.username}")
                except Exception as e:
                    logger.error(f"Failed to refresh token for user {self.user.username}: {e}")
                    # Auto-disable calendar sync if refresh fails
                    self.user.calendar_sync_enabled = False
                    self.user.save()
                    return None
            
            return creds
            
        except Exception as e:
            logger.error(f"Error getting credentials for user {self.user.username}: {e}")
            return None
    
    def _get_service(self):
        """Get Google Calendar service instance."""
        if self.service is not None:
            return self.service
            
        creds = self._get_credentials()
        if not creds:
            return None
            
        try:
            self.service = build('calendar', 'v3', credentials=creds)
            return self.service
        except Exception as e:
            logger.error(f"Error building calendar service for user {self.user.username}: {e}")
            return None
    
    def test_connection(self) -> bool:
        """Test if we can connect to Google Calendar API."""
        try:
            service = self._get_service()
            if not service:
                return False
                
            # Try to get calendar info
            calendar = service.calendars().get(calendarId=self.calendar_id).execute()
            logger.info(f"Successfully connected to calendar '{calendar.get('summary', 'Unknown')}' for user {self.user.username}")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error testing calendar connection for user {self.user.username}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error testing calendar connection for user {self.user.username}: {e}")
            return False
    
    def _match_to_event(self, match: Match) -> Dict[str, Any]:
        """Convert a Match object to Google Calendar event format."""
        
        # Crear título del evento
        title = f"[VOLEIBOL] {match.home_team.name} vs {match.away_team.name}"
        if match.league:
            title += f" - {match.league.name}"
        
        # Descripción del evento
        description_parts = []
        if match.league:
            description_parts.append(f"Liga: {match.league.name}")
            if match.league.category:
                description_parts.append(f"Categoría: {match.league.category.name}")
        
        if match.venue:
            description_parts.append(f"Lugar: {match.venue}")
        
        if match.city:
            description_parts.append(f"Ciudad: {match.city}")
            
        description_parts.append(f"Jornada: {match.round_number}")
        
        # Añadir enlace a la página del partido
        if hasattr(settings, 'SITE_URL'):
            match_url = f"{settings.SITE_URL}/videos/partidos/{match.id}/"
            description_parts.append(f"\nVer detalles: {match_url}")
        
        description = "\n".join(description_parts)
        
        # Configurar fechas
        start_time = match.match_date
        end_time = start_time + timedelta(hours=2)  # Duración estimada de 2 horas
        
        # Convertir a formato ISO
        timezone_name = getattr(settings, 'GOOGLE_CALENDAR_TIMEZONE', 'Europe/Madrid')
        
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': timezone_name,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': timezone_name,
            },
            'location': f"{match.venue}, {match.city}" if match.venue and match.city else (match.venue or match.city or ""),
            'source': {
                'title': 'VideosVoley',
                'url': f"{getattr(settings, 'SITE_URL', '')}/videos/partidos/{match.id}/" if hasattr(settings, 'SITE_URL') else ""
            },
            'extendedProperties': {
                'private': {
                    'videosvoley_match_id': str(match.id),
                    'videosvoley_federation_id': match.federation_id or "",
                }
            }
        }
        
        return event
    
    def create_event(self, match: Match) -> Optional[str]:
        """Create a calendar event for a match. Returns event ID if successful."""
        if not settings.GOOGLE_CALENDAR_ENABLED:
            logger.info("Google Calendar sync is disabled in settings")
            return None
            
        service = self._get_service()
        if not service:
            logger.error(f"Could not get calendar service for user {self.user.username}")
            return None
            
        try:
            event = self._match_to_event(match)
            created_event = service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            logger.info(f"Created calendar event {event_id} for match {match.id} (user: {self.user.username})")
            return event_id
            
        except HttpError as e:
            logger.error(f"HTTP error creating calendar event for match {match.id}, user {self.user.username}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating calendar event for match {match.id}, user {self.user.username}: {e}")
            return None
    
    def update_event(self, event_id: str, match: Match) -> bool:
        """Update an existing calendar event. Returns True if successful."""
        if not settings.GOOGLE_CALENDAR_ENABLED:
            return False
            
        service = self._get_service()
        if not service:
            return False
            
        try:
            event = self._match_to_event(match)
            service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Updated calendar event {event_id} for match {match.id} (user: {self.user.username})")
            return True
            
        except HttpError as e:
            logger.error(f"HTTP error updating calendar event {event_id} for match {match.id}, user {self.user.username}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating calendar event {event_id} for match {match.id}, user {self.user.username}: {e}")
            return False
    
    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event. Returns True if successful."""
        if not settings.GOOGLE_CALENDAR_ENABLED:
            return False
            
        service = self._get_service()
        if not service:
            return False
            
        try:
            service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            logger.info(f"Deleted calendar event {event_id} (user: {self.user.username})")
            return True
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.info(f"Calendar event {event_id} already deleted (user: {self.user.username})")
                return True
            logger.error(f"HTTP error deleting calendar event {event_id}, user {self.user.username}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting calendar event {event_id}, user {self.user.username}: {e}")
            return False
    
    def find_events_by_match(self, match: Match) -> List[Dict[str, Any]]:
        """Find calendar events for a specific match."""
        if not settings.GOOGLE_CALENDAR_ENABLED:
            return []
            
        service = self._get_service()
        if not service:
            return []
            
        try:
            # Buscar eventos en un rango de tiempo alrededor del partido
            time_min = (match.match_date - timedelta(hours=1)).isoformat()
            time_max = (match.match_date + timedelta(hours=5)).isoformat()
            
            events_result = service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Filtrar por match ID en las propiedades extendidas
            match_events = []
            for event in events:
                extended_props = event.get('extendedProperties', {}).get('private', {})
                if extended_props.get('videosvoley_match_id') == str(match.id):
                    match_events.append(event)
            
            return match_events
            
        except HttpError as e:
            logger.error(f"HTTP error finding events for match {match.id}, user {self.user.username}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error finding events for match {match.id}, user {self.user.username}: {e}")
            return []
    
    def sync_user_matches(self, force: bool = False) -> Dict[str, int]:
        """Sync all matches for user's preferred categories."""
        if not self.user.can_sync_calendar():
            logger.info(f"User {self.user.username} cannot sync calendar")
            return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        if not settings.GOOGLE_CALENDAR_ENABLED:
            logger.info("Google Calendar sync is disabled in settings")
            return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        # Obtener partidos de las categorías preferidas del usuario
        user_categories = self.user.preferred_categories.all()
        
        # Filtrar partidos futuros o recientes (último mes hacia adelante)
        cutoff_date = timezone.now() - timedelta(days=30)
        matches = Match.objects.filter(
            league__category__in=user_categories,
            match_date__gte=cutoff_date
        ).select_related('home_team', 'away_team', 'league__category')
        
        logger.info(f"Syncing {matches.count()} matches for user {self.user.username}")
        
        for match in matches:
            try:
                # Buscar eventos existentes para este partido
                existing_events = self.find_events_by_match(match)
                
                if existing_events:
                    # Actualizar el primer evento encontrado
                    event_id = existing_events[0].get('id')
                    if self.update_event(event_id, match):
                        stats['updated'] += 1
                    else:
                        stats['errors'] += 1
                        
                    # Eliminar eventos duplicados si los hay
                    for extra_event in existing_events[1:]:
                        self.delete_event(extra_event.get('id'))
                else:
                    # Crear nuevo evento
                    event_id = self.create_event(match)
                    if event_id:
                        stats['created'] += 1
                    else:
                        stats['errors'] += 1
                        
            except Exception as e:
                logger.error(f"Error syncing match {match.id} for user {self.user.username}: {e}")
                stats['errors'] += 1
        
        # Actualizar timestamp de última sincronización
        self.user.calendar_last_sync = timezone.now()
        self.user.save(update_fields=['calendar_last_sync'])
        
        logger.info(f"Calendar sync completed for user {self.user.username}: {stats}")
        return stats


def get_calendar_service(user) -> Optional[GoogleCalendarService]:
    """Factory function to get a calendar service for a user."""
    if not user or not user.is_authenticated:
        return None
        
    return GoogleCalendarService(user)