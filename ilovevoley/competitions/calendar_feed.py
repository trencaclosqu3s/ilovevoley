from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Q
from django.http import Http404
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django_ical.feedgenerator import ICal20Feed
from django_ical.views import ICalFeed

from ilovevoley.competitions.models import Match
from ilovevoley.competitions.services.venue_service import get_match_location_info
from ilovevoley.core.mixins import get_club_team_filter
from ilovevoley.core.models import Category, Organization
from ilovevoley.users.models import User


APPLE_LOCATION_RADIUS_METERS = 70


class AppleLocationFeed(ICal20Feed):
    """Añade X-APPLE-STRUCTURED-LOCATION a los eventos que traen `apple_location`.

    Es la propiedad que Calendar de iOS/macOS usa para mostrar mapa y tiempo de trayecto;
    django-ical no soporta propiedades X- arbitrarias. LOCATION y GEO se mantienen para
    Google Calendar y Outlook.
    """

    def write_items(self, calendar):
        super().write_items(calendar)
        # Los componentes se añaden en el mismo orden que self.items.
        for element, item in zip(calendar.subcomponents, self.items):
            apple_location = item.get('apple_location')
            if apple_location:
                element.add(
                    'X-APPLE-STRUCTURED-LOCATION',
                    f'geo:{apple_location["latitude"]},{apple_location["longitude"]}',
                    parameters={
                        'VALUE': 'URI',
                        'X-ADDRESS': apple_location['address'],
                        'X-APPLE-RADIUS': str(APPLE_LOCATION_RADIUS_METERS),
                        'X-TITLE': apple_location['title'],
                    },
                )


class UserMatchesFeed(ICalFeed):
    """
    Feed de calendario iCal para partidos filtrados por categorías preferidas del usuario
    y limitado a las organizaciones donde el usuario tiene membresía aprobada.
    """

    product_id = '-//I Love Voley//Calendario de Partidos//ES'
    timezone = 'Europe/Madrid'
    file_name = 'partidos.ics'
    feed_type = AppleLocationFeed

    def get_object(self, request, token):
        try:
            user = User.objects.get(calendar_token=token, is_active=True)
            return user
        except User.DoesNotExist:
            raise Http404("Token de calendario inválido")

    def title(self, obj):
        return f'I Love Voley - Partidos de {obj.username}'

    @staticmethod
    def _preferred_categories(user, organizations):
        """Une las categorías de interés del usuario en varios clubes.

        El feed no tiene un tenant activo: agrupa las preferencias de todas las
        organizaciones (con membresía aprobada) del usuario.
        """
        return Category.objects.filter(
            category_preferences__user=user,
            category_preferences__organization__in=organizations,
        ).distinct()

    def description(self, obj):
        orgs = Organization.objects.filter(memberships__user=obj, memberships__is_approved=True)
        categories = self._preferred_categories(obj, orgs)
        parts = []
        if orgs:
            parts.append(', '.join([o.name for o in orgs]))
        if categories:
            parts.append(', '.join([c.name for c in categories]))
        return f'Calendario de partidos: {" · ".join(parts)}' if parts else 'Calendario de partidos de voleibol'

    def items(self, obj):
        """
        Muestra los partidos que cumplen ambas condiciones:
        1. La categoría de la liga está entre las categorías preferidas del usuario.
        2. Uno de los equipos pertenece a una organización donde el usuario tiene membresía aprobada.
        """
        approved_orgs = Organization.objects.filter(
            memberships__user=obj,
            memberships__is_approved=True
        )
        categories = self._preferred_categories(obj, approved_orgs)
        if not categories.exists():
            return Match.objects.none()

        if not approved_orgs.exists():
            return Match.objects.none()

        # Combinar filtros de equipo de todas las organizaciones del usuario
        team_filter = Q()
        for org in approved_orgs:
            team_filter |= get_club_team_filter(org)

        start_date = timezone.now() - timedelta(days=30)
        end_date = timezone.now() + timedelta(days=365)

        return Match.objects.filter(
            Q(league__categories__in=categories) | Q(is_friendly=True),
            match_date__gte=start_date,
            match_date__lte=end_date,
        ).filter(
            team_filter
        ).select_related(
            'home_team',
            'home_team__club',
            'home_team__club__default_venue',
            'away_team',
            'league',
            'venue_ref',
        ).prefetch_related(
            'league__categories'
        ).distinct().order_by('match_date')

    def item_guid(self, item):
        """
        ID único para cada evento en el feed ICS (propiedad UID de RFC 5545).

        NOTA DE COMPATIBILIDAD (Issue #105 / M-045):
        Por defecto se mantiene el dominio '@videosvoley.com' como namespace del GUID.
        Los clientes de calendario (Google Calendar, Apple Calendar, Outlook, etc.)
        utilizan el UID como identificador único persistente para asociar eventos
        existentes y actualizar cambios de fecha u hora sin duplicados.
        Modificar este sufijo en producción provocaría que los calendarios ya suscritos
        interpreten todos los partidos como eventos nuevos, duplicándolos en la agenda.
        Se permite configurar un dominio alternativo mediante el setting
        CALENDAR_FEED_DOMAIN para instalaciones nuevas o migraciones controladas.
        """
        domain = getattr(settings, 'CALENDAR_FEED_DOMAIN', 'videosvoley.com')
        return f'partido-{item.id}@{domain}'

    def item_title(self, item):
        """Título del evento"""
        # Incluir categorías en el título para mejor visibilidad
        categories = []
        if item.league:
            categories = list(item.league.categories.all())
        category_name = ', '.join([c.name for c in categories]) if categories else 'Sin Categoría'

        # Prefijo para partidos cancelados
        prefix = ''
        if item.status == 'cancelled':
            prefix = '❌ CANCELADO - '

        title = f'{prefix}🏐 [{category_name}] {item.home_team_display} vs {item.away_team_display}'

        # Añadir indicador de amistoso
        if item.is_friendly:
            title = f'🏐 {title} [AMISTOSO]'

        # Marcar como PROVISIONAL si la hora es 00:00 (indica que no está confirmada)
        if item.match_date.hour == 0 and item.match_date.minute == 0:
            title = f'{title} [PROVISIONAL]'

        return title

    def item_description(self, item):
        """Descripción del evento"""
        description_parts = []

        # Advertencia si está cancelado
        if item.status == 'cancelled':
            description_parts.append('❌ PARTIDO CANCELADO')
            description_parts.append('')

        # Advertencia si es provisional
        if item.match_date.hour == 0 and item.match_date.minute == 0:
            description_parts.append('⚠️ HORARIO PROVISIONAL - Pendiente de confirmación')
            description_parts.append('')

        if item.league:
            description_parts.append(f'Liga: {item.league.name}')
        else:
            description_parts.append('Liga: Amistoso')

        # Agregar todas las categorías
        if item.league:
            categories = list(item.league.categories.all())
            if categories:
                category_names = ', '.join([c.name for c in categories])
                description_parts.append(f'Categoría: {category_names}')
        elif item.is_friendly:
            description_parts.append('Categoría: Amistoso')

        if item.round_number:
            description_parts.append(f'Jornada: {item.round_number}')

        if item.home_score is not None and item.away_score is not None:
            description_parts.append(f'Resultado: {item.home_score} - {item.away_score}')

        # Bloque de ubicación y enlace a mapa
        info = self._location_info(item)
        if info['location_text'] and info['location_text'] != 'Por confirmar':
            description_parts.append('')
            description_parts.append(f'📍 Ubicación: {info["location_text"]}')
            if info['maps_url']:
                description_parts.append(f'🗺️ Cómo llegar: {info["maps_url"]}')

        # Agregar enlace al partido en la web
        try:
            match_url = reverse("competitions:match_detail", args=[item.id])
            description_parts.append(f'\nVer más información en la web: {match_url}')
        except NoReverseMatch:
            pass

        return '\n'.join(description_parts)

    def item_start_datetime(self, item):
        """Fecha y hora de inicio del evento"""
        match_time = item.match_date

        if match_time.hour == 0 and match_time.minute == 0:
            provisional_time = match_time.replace(hour=9, minute=0)
            return provisional_time

        return match_time

    def item_end_datetime(self, item):
        """Fecha y hora de fin del evento (2 horas después del inicio)"""
        start = self.item_start_datetime(item)
        return start + timedelta(hours=2)

    @staticmethod
    def _location_info(item):
        """Resuelve la ubicación una sola vez por partido (description, location y coordenadas la usan)."""
        if not hasattr(item, '_location_info'):
            item._location_info = get_match_location_info(item)
        return item._location_info

    def item_location(self, item):
        """Ubicación del evento normalizada para clientes de calendario (RFC 5545)."""
        return self._location_info(item)['location_text']

    def item_geolocation(self, item):
        """Coordenadas (GEO, RFC 5545) de la sede; None si no se conocen."""
        venue = self._location_info(item)['venue']
        if venue and venue.latitude is not None and venue.longitude is not None:
            return float(venue.latitude), float(venue.longitude)
        return None

    def item_extra_kwargs(self, item):
        kwargs = super().item_extra_kwargs(item)
        venue = self._location_info(item)['venue']
        if venue and venue.latitude is not None and venue.longitude is not None:
            kwargs['apple_location'] = {
                'latitude': venue.latitude,
                'longitude': venue.longitude,
                'title': venue.name,
                'address': venue.full_address,
            }
        return kwargs

    def item_link(self, item):
        """Enlace al partido en la web"""
        try:
            return reverse("competitions:match_detail", args=[item.id])
        except:
            return None

    def item_created(self, item):
        """Fecha de creación del evento"""
        if hasattr(item, 'created_at') and item.created_at:
            return item.created_at
        return timezone.now()

    def item_updateddate(self, item):
        """Fecha de última actualización del evento"""
        if hasattr(item, 'updated_at') and item.updated_at:
            return item.updated_at
        return timezone.now()
