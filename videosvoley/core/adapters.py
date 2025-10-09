"""
Custom allauth adapters for Google OAuth with optional Calendar permissions.
"""
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.conf import settings


class GoogleCalendarSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to handle optional Google Calendar permissions.
    """
    
    def get_provider_scope(self, request, provider):
        """
        Override scope based on user request for calendar permissions.
        """
        scope = super().get_provider_scope(request, provider)
        
        # Solo añadir Calendar scope si el usuario lo solicita explícitamente
        if (provider == 'google' and 
            request.GET.get('calendar') == 'true' and
            settings.GOOGLE_CALENDAR_ENABLED):
            
            # Convertir scope a lista si es string
            if isinstance(scope, str):
                scope = scope.split()
            elif scope is None:
                scope = settings.GOOGLE_BASIC_SCOPES.copy()
            else:
                scope = list(scope)
            
            # Añadir Calendar scope si no está ya incluido
            if settings.GOOGLE_CALENDAR_SCOPE not in scope:
                scope.append(settings.GOOGLE_CALENDAR_SCOPE)
        
        return scope