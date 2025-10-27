"""
Forms para la gestión de competiciones (ligas, partidos, clasificaciones).
Migrados desde videos.forms para la nueva app competitions.
"""
from django import forms
from django.conf import settings
from django.db.models import Q
from .models import League, Match, Standing

# Importar modelos de otras apps
from videosvoley.content.models import Category
from videosvoley.teams.models import Team


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
                league = League.objects.get(id=self.data['league'])
                league_category = league.category
                if self.data and 'filter_by_category' in self.data:
                    filter_by_category = self.data.get('filter_by_category') == 'on'
            except League.DoesNotExist:
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


class FriendlyMatchForm(forms.ModelForm):
    """Formulario para crear partidos amistosos desde el calendario"""
    
    # Campo para seleccionar categoría (requerido)
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=True,
        label='Categoría',
        help_text='Selecciona la categoría del partido',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_category'
        })
    )
    
    class Meta:
        model = Match
        fields = ['home_team_text', 'away_team_text', 'match_date', 'venue']
        widgets = {
            'home_team_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Equipo local',
                'id': 'id_home_team_text'
            }),
            'away_team_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Equipo visitante',
                'id': 'id_away_team_text'
            }),
            'match_date': forms.DateTimeInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'type': 'datetime-local',
                'id': 'id_match_date'
            }),
            'venue': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Polideportivo, pabellón, etc.',
                'id': 'id_venue'
            }),
        }
        labels = {
            'home_team_text': 'Equipo Local',
            'away_team_text': 'Equipo Visitante',
            'match_date': 'Fecha y Hora',
            'venue': 'Lugar',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hacer campos opcionales
        self.fields['venue'].required = False
        self.fields['notes'].required = False
        
        # Configurar queryset de categorías activas
        self.fields['category'].queryset = Category.objects.filter(is_active=True).order_by('name')

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        home_team_text = cleaned_data.get('home_team_text')
        away_team_text = cleaned_data.get('away_team_text')
        match_date = cleaned_data.get('match_date')
        
        # Validar que los equipos sean diferentes
        if home_team_text and away_team_text and home_team_text.strip().lower() == away_team_text.strip().lower():
            raise forms.ValidationError('Los equipos local y visitante deben ser diferentes')
        
        # Validar que la fecha no sea en el pasado (con margen de 1 hora)
        if match_date:
            from django.utils import timezone
            now = timezone.now()
            if match_date < now:
                raise forms.ValidationError('La fecha del partido no puede ser en el pasado')
        
        return cleaned_data

    def save(self, commit=True):
        """Guardar el partido amistoso con configuración automática"""
        match = super().save(commit=False)
        
        # Configurar como partido amistoso
        match.competition_type = 'friendly'
        match.status = 'scheduled'
        
        # Crear liga amistosa si no existe
        if not match.league:
            friendly_league, created = League.objects.get_or_create(
                name='Partidos Amistosos',
                defaults={
                    'competition_type': 'friendly',
                    'season': '2024-25',
                    'is_active': True,
                    'description': 'Partidos amistosos del club'
                }
            )
            match.league = friendly_league
        
        if commit:
            match.save()
        
        return match


class MatchResultForm(forms.ModelForm):
    """Formulario para agregar resultado de partido"""
    
    class Meta:
        model = Match
        fields = ['home_score', 'away_score', 'status']
        widgets = {
            'home_score': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0',
                'max': '99',
                'placeholder': '0'
            }),
            'away_score': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0',
                'max': '99',
                'placeholder': '0'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
        }
        labels = {
            'home_score': 'Goles Local',
            'away_score': 'Goles Visitante',
            'status': 'Estado',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar opciones de estado
        self.fields['status'].choices = [
            ('finished', 'Finalizado'),
            ('in_progress', 'En curso'),
            ('scheduled', 'Programado'),
            ('postponed', 'Aplazado'),
            ('cancelled', 'Cancelado'),
        ]

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        home_score = cleaned_data.get('home_score')
        away_score = cleaned_data.get('away_score')
        status = cleaned_data.get('status')
        
        # Si el partido está finalizado, validar que tenga resultado
        if status == 'finished':
            if home_score is None or away_score is None:
                raise forms.ValidationError('Un partido finalizado debe tener resultado completo')
            
            # Validar que los goles sean números positivos
            if home_score < 0 or away_score < 0:
                raise forms.ValidationError('Los goles no pueden ser negativos')
        
        return cleaned_data


class LeagueForm(forms.ModelForm):
    """Formulario para crear/editar ligas"""
    
    class Meta:
        model = League
        fields = ['name', 'season', 'competition_type', 'category', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre de la liga'
            }),
            'season': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': '2024-25'
            }),
            'competition_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
            }),
        }
        labels = {
            'name': 'Nombre',
            'season': 'Temporada',
            'competition_type': 'Tipo de Competición',
            'category': 'Categoría',
            'is_active': 'Activa',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar queryset de categorías activas
        self.fields['category'].queryset = Category.objects.filter(is_active=True).order_by('name')


class StandingForm(forms.ModelForm):
    """Formulario para crear/editar clasificaciones"""
    
    class Meta:
        model = Standing
        fields = ['team', 'position', 'played', 'won', 'lost', 'sets_for', 'sets_against', 'points_for', 'points_against', 'total_points']
        widgets = {
            'team': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'position': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '1'
            }),
            'played': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'won': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'lost': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'sets_for': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'sets_against': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'points_for': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'points_against': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
            'total_points': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '0'
            }),
        }
        labels = {
            'team': 'Equipo',
            'position': 'Posición',
            'played': 'Partidos Jugados',
            'won': 'Partidos Ganados',
            'lost': 'Partidos Perdidos',
            'sets_for': 'Sets a Favor',
            'sets_against': 'Sets en Contra',
            'points_for': 'Puntos a Favor',
            'points_against': 'Puntos en Contra',
            'total_points': 'Puntos Totales',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar queryset de equipos activos
        self.fields['team'].queryset = Team.objects.filter(is_active=True).order_by('name')

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        matches_played = cleaned_data.get('matches_played', 0)
        matches_won = cleaned_data.get('matches_won', 0)
        matches_drawn = cleaned_data.get('matches_drawn', 0)
        matches_lost = cleaned_data.get('matches_lost', 0)
        
        # Validar que la suma de partidos ganados, empatados y perdidos sea igual a partidos jugados
        if matches_played is not None and matches_won is not None and matches_drawn is not None and matches_lost is not None:
            total_matches = matches_won + matches_drawn + matches_lost
            if total_matches != matches_played:
                raise forms.ValidationError(
                    f'La suma de partidos ganados ({matches_won}), empatados ({matches_drawn}) y perdidos ({matches_lost}) '
                    f'debe ser igual a los partidos jugados ({matches_played})'
                )
        
        return cleaned_data