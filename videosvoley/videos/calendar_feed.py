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
            match_date__gte=start_date,
            match_date__lte=end_date
        ).select_related(
            'home_team',
            'away_team',
            'category',
            'league'
        ).order_by('match_date')
        
        return matches
    
    def item_guid(self, item):
        """ID único para cada evento (importante para actualizaciones)"""
        return f'partido-{item.id}@videosvoley.com'
    
    def item_title(self, item):
        """Título del evento"""
        # Incluir categoría en el título para mejor visibilidad
        title = f'🏐 [{item.category.name}] {item.home_team.name} vs {item.away_team.name}'
        
        # Marcar como PROVISIONAL si la hora es 00:00 (indica que no está confirmada)
        if item.match_date.hour == 0 and item.match_date.minute == 0:
            title = f'{title} [PROVISIONAL]'
        
        return title
    
    def item_description(self, item):
        """Descripción del evento"""
        description_parts = []
        
        # Advertencia si es provisional
        if item.match_date.hour == 0 and item.match_date.minute == 0:
            description_parts.append('⚠️ HORARIO PROVISIONAL - Pendiente de confirmación')
            description_parts.append('')
        
        description_parts.extend([
            f'Liga: {item.league.name}',
            f'Categoría: {item.category.name}',
        ])
        
        if item.round_number:
            description_parts.append(f'Jornada: {item.round_number}')
        
        if item.home_score is not None and item.away_score is not None:
            description_parts.append(f'Resultado: {item.home_score} - {item.away_score}')
        
        # Agregar enlace al partido en la web
        try:
            match_url = reverse("videos:match_detail", args=[item.id])
            description_parts.append(f'\nVer más información en la web')
        except:
            pass
        
        return '\n'.join(description_parts)
    
    def item_start_datetime(self, item):
        """Fecha y hora de inicio del evento"""
        # Si la hora es 00:00, considerarlo como provisional y poner a las 09:00
        # para que aparezca al inicio del día y sea más visible
        if item.match_date.hour == 0 and item.match_date.minute == 0:
            provisional_time = item.match_date.replace(hour=9, minute=0)
            return provisional_time
        
        return item.match_date
    
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
