from django import forms
from django.conf import settings
from django.db.models import Q
from .models import Video, Comment, Category, Match


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ['title', 'youtube_url', 'description', 'category', 'match']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ej: Partido vs Pòrtol  - 15/10/2025'
            }),
            'youtube_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://www.youtube.com/watch?v=...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Descripción opcional del partido'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'match': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
        }
        labels = {
            'title': 'Título',
            'youtube_url': 'URL de YouTube',
            'description': 'Descripción',
            'category': 'Categoría',
            'match': 'Partido (opcional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer el campo match opcional
        self.fields['match'].required = False
        
        # Filtrar partidos inteligentemente basado en categoría y equipos del club
        self._setup_match_queryset()
        
    def _setup_match_queryset(self):
        """Configura el queryset de partidos basado en categoría y equipos del club"""
        # Obtener configuración de equipos
        club_team_names = getattr(settings, 'CLUB_TEAM_NAMES', {})
        default_team = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        
        # Si hay una categoría preseleccionada, filtrar por equipos de esa categoría
        category = None
        if self.data and 'category' in self.data:
            try:
                from .models import Category
                category = Category.objects.get(id=self.data['category'])
            except (Category.DoesNotExist, ValueError):
                pass
        elif self.instance and self.instance.category:
            category = self.instance.category
        
        # Determinar nombres de equipos a buscar
        team_names = []
        if category:
            category_key = category.name.lower()
            if category_key in club_team_names:
                team_names = club_team_names[category_key]
                if isinstance(team_names, str):
                    team_names = [team_names]
            else:
                # Buscar equipos que contengan tanto el nombre de la categoría como SANT JOSEP
                team_names = [f"SANT JOSEP {category.name.upper()}", f"CV SANT JOSEP {category.name.upper()}"]
        
        # Si no hay categoría específica o no se encontraron equipos, usar configuración por defecto
        if not team_names:
            default_names = club_team_names.get('default', default_team)
            if isinstance(default_names, str):
                team_names = [default_names]
            else:
                team_names = default_names
        
        # Construir query para buscar cualquiera de los nombres de equipo
        team_query = Q()
        for team_name in team_names:
            team_query |= Q(home_team__name__icontains=team_name) | Q(away_team__name__icontains=team_name)
        
        # Si hay categoría, también filtrar por ligas de esa categoría
        if category:
            team_query &= Q(league__category=category)
        
        self.fields['match'].queryset = Match.objects.select_related(
            'home_team', 'away_team', 'league', 'league__category'
        ).filter(team_query).order_by('-match_date')
        
        # Actualizar label basado en contexto
        if category:
            self.fields['match'].empty_label = f"Seleccionar partido de {category.name} (opcional)"
        else:
            self.fields['match'].empty_label = "Seleccionar partido del club (opcional)"


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent resize-none',
                'rows': 2,
                'placeholder': '¡Añade un comentario de apoyo! 💪'
            }),
        }
        labels = {
            'content': '',
        }