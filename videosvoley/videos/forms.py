from django import forms
from django.conf import settings
from django.db.models import Q
from .models import Video, Comment, Category, Match, Team


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
        # Obtener configuración de equipos del club
        club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        
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
        
        # Construir query base para equipos del club
        club_query = (Q(home_team__name__icontains=club_team_name) | 
                     Q(away_team__name__icontains=club_team_name))
        
        # Si hay categoría específica, filtrar por equipos de esa categoría
        if category:
            # Filtrar por equipos que tengan la categoría específica O por liga de esa categoría
            category_query = (Q(home_team__category=category) | Q(away_team__category=category) |
                            Q(league__category=category))
            
            # Combinar: partidos del club Y de la categoría específica
            final_query = club_query & category_query
            
        else:
            # Sin categoría específica, mostrar todos los partidos del club
            final_query = club_query
        
        self.fields['match'].queryset = Match.objects.select_related(
            'home_team', 'away_team', 'home_team__category', 'away_team__category', 
            'league', 'league__category'
        ).filter(final_query).order_by('-match_date')
        
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


class MatchAdminForm(forms.ModelForm):
    """Formulario personalizado para el admin de Match con filtrado por categoría"""
    
    filter_by_category = forms.BooleanField(
        required=False, 
        initial=True,
        label='Filtrar equipos por categoría de la liga',
        help_text='Desmarca para ver todos los equipos disponibles'
    )
    
    class Meta:
        model = Match
        fields = '__all__'
        widgets = {
            'match_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar filtrado por defecto
        filter_by_category = True
        league_category = None
        
        # Si estamos editando un match existente y tiene liga
        if self.instance and self.instance.pk and self.instance.league:
            league_category = self.instance.league.category
            
            # Verificar si se envió el formulario con el checkbox
            if self.data and 'filter_by_category' in self.data:
                filter_by_category = self.data.get('filter_by_category') == 'on'
        
        # Si hay datos POST sobre league, obtener la categoría de esa liga
        elif self.data and 'league' in self.data and self.data['league']:
            try:
                from .models import League
                league = League.objects.get(id=self.data['league'])
                league_category = league.category
                if self.data and 'filter_by_category' in self.data:
                    filter_by_category = self.data.get('filter_by_category') == 'on'
            except (League.DoesNotExist, ValueError):
                pass
        
        # Aplicar filtrado de equipos
        if filter_by_category and league_category:
            # Filtrar equipos por la categoría de la liga
            filtered_teams = Team.objects.filter(category=league_category).order_by('name')
            self.fields['home_team'].queryset = filtered_teams
            self.fields['away_team'].queryset = filtered_teams
            
            # Actualizar help text
            self.fields['home_team'].help_text = f'Equipos de la categoría: {league_category.name}'
            self.fields['away_team'].help_text = f'Equipos de la categoría: {league_category.name}'
        else:
            # Mostrar todos los equipos
            self.fields['home_team'].queryset = Team.objects.all().order_by('name')
            self.fields['away_team'].queryset = Team.objects.all().order_by('name')
        
        # Agregar clases CSS y atributos para JavaScript
        self.fields['filter_by_category'].widget.attrs.update({
            'id': 'id_filter_by_category'
        })
        
        # Establecer valor inicial del checkbox
        if 'filter_by_category' not in self.data:
            self.fields['filter_by_category'].initial = True