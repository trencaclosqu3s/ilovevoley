# videosvoley/videos/calendar_feed.py
from django.http import Http404
from django.utils import timezone
from django_ical.views import ICalFeed
from django.urls import reverse
from videosvoley.videos.models import Match
from videosvoley.users.models import User
from datetime import timedelta, datetime, time


class UserMatchesFeed(ICalFeed):
    """
    Feed de calendario iCal para partidos filtrados por categorías preferidas del usuario.
    Genera un archivo .ics que se puede suscribir desde cualquier aplicación de calendario.
    """
    
    product_id = '-//VideosVoley//Calendario de Partidos//ES'
    timezone = 'Europe/Madrid'
    file_name = 'partidos.ics'
    
    def get_object(self, request, token):
        """
        Obtiene el usuario basado en el token único.
        """
        try:
            user = User.objects.get(calendar_token=token, is_active=True)
            return user
        except User.DoesNotExist:
            raise Http404("Token de calendario inválido")
    
    def title(self, obj):
        """Título del calendario"""
        return f'VideosVoley - Partidos de {obj.username}'
    
    def description(self, obj):
        """Descripción del calendario"""
        categories = obj.preferred_categories.all()
        if categories:
            cat_names = ', '.join([c.name for c in categories])
            return f'Calendario de partidos de las categorías: {cat_names}'
        return 'Calendario de partidos de voleibol'
    
    def items(self, obj):
        """
        Retorna los partidos que coinciden con las categorías preferidas del usuario.
        Filtra partidos desde 30 días atrás hasta 1 año adelante.
        """
        categories = obj.preferred_categories.all()
        
        if not categories:
            # Si no tiene categorías, no mostrar nada
            return Match.objects.none()
        
        # Rango de fechas: 30 días atrás hasta 1 año adelante
        start_date = timezone.now() - timedelta(days=30)
        end_date = timezone.now() + timedelta(days=365)
        
        # Filtrar partidos por categorías preferidas
        matches = Match.objects.filter(
            category__in=categories,
            date__gte=start_date,
            date__lte=end_date
        ).select_related(
            'home_team',
            'away_team',
            'category',
            'league'
        ).order_by('date', 'time')
        
        return matches
    
    def item_guid(self, item):
        """ID único para cada evento (importante para actualizaciones)"""
        return f'partido-{item.id}@videosvoley.com'
    
    def item_title(self, item):
        """Título del evento"""
        return f'[VOLEIBOL] {item.home_team.name} vs {item.away_team.name}'
    
    def item_description(self, item):
        """Descripción del evento"""
        description_parts = [
            f'Liga: {item.league.name}',
            f'Categoría: {item.category.name}',
        ]
        
        if item.round_name:
            description_parts.append(f'Jornada: {item.round_name}')
        
        if item.result:
            description_parts.append(f'Resultado: {item.result}')
        
        # Agregar enlace al partido en la web (usa dominio relativo por ahora)
        try:
            match_url = reverse("videos:match_detail", args=[item.id])
            description_parts.append(f'\nVer más información en la web')
        except:
            pass
        
        return '\n'.join(description_parts)
    
    def item_start_datetime(self, item):
        """Fecha y hora de inicio del evento"""
        if item.time:
            # Combinar fecha y hora
            dt = datetime.combine(item.date, item.time)
            # Hacer timezone-aware
            return timezone.make_aware(dt, timezone.get_current_timezone())
        else:
            # Si no hay hora, usar las 18:00 como default
            dt = datetime.combine(item.date, time(18, 0))
            return timezone.make_aware(dt, timezone.get_current_timezone())
    
    def item_end_datetime(self, item):
        """Fecha y hora de fin del evento (2 horas después del inicio)"""
        start = self.item_start_datetime(item)
        return start + timedelta(hours=2)
    
    def item_location(self, item):
        """Ubicación del evento"""
        location_parts = []
        
        if item.venue:
            location_parts.append(item.venue)
        
        if item.city:
            location_parts.append(item.city)
        
        return ', '.join(location_parts) if location_parts else 'Por confirmar'
    
    def item_link(self, item):
        """Enlace al partido en la web"""
        try:
            return reverse("videos:match_detail", args=[item.id])
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
