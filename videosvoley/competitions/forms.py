from django import forms
from django.utils import timezone
from .models import League, Match, Standing, ScrapingEndpoint


class LeagueForm(forms.ModelForm):
    """Formulario para crear/editar ligas"""
    class Meta:
        model = League
        fields = [
            'name', 'federation_id', 'competition_type', 'season', 'category',
            'visibility_type', 'is_active', 'is_historical', 'is_our_team_related',
            'match_format', 'custom_max_sets', 'custom_sets_to_win', 'base_url'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre de la liga'
            }),
            'federation_id': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'ID de la federación'
            }),
            'season': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ej: 2024-25'
            }),
            'competition_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'visibility_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'match_format': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'base_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://www.voleibolib.net'
            }),
        }
        labels = {
            'name': 'Nombre de la Liga',
            'federation_id': 'ID de la Federación',
            'competition_type': 'Tipo de Competición',
            'season': 'Temporada',
            'category': 'Categoría',
            'visibility_type': 'Tipo de Visibilidad',
            'is_active': 'Activa',
            'is_historical': 'Histórica',
            'is_our_team_related': 'Relacionada con Nuestro Equipo',
            'match_format': 'Formato de Partido',
            'custom_max_sets': 'Máximo de Sets (Personalizado)',
            'custom_sets_to_win': 'Sets para Ganar (Personalizado)',
            'base_url': 'URL Base',
        }


class MatchForm(forms.ModelForm):
    """Formulario para crear/editar partidos"""
    class Meta:
        model = Match
        fields = [
            'league', 'home_team', 'away_team', 'home_team_text', 'away_team_text',
            'is_friendly', 'match_date', 'venue', 'city', 'round_number',
            'home_score', 'away_score', 'status', 'federation_id',
            'referee1', 'referee2', 'scorer', 'timekeeper', 'delegate',
            'field_address', 'federation_club_local_id', 'federation_club_away_id',
            'acta_html'
        ]
        widgets = {
            'match_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'venue': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del pabellón'
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ciudad'
            }),
            'home_team_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del equipo local'
            }),
            'away_team_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del equipo visitante'
            }),
            'home_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 0
            }),
            'away_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 0
            }),
            'round_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 1
            }),
            'field_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Dirección completa del campo'
            }),
        }
        labels = {
            'league': 'Liga',
            'home_team': 'Equipo Local',
            'away_team': 'Equipo Visitante',
            'home_team_text': 'Equipo Local (Texto)',
            'away_team_text': 'Equipo Visitante (Texto)',
            'is_friendly': 'Partido Amistoso',
            'match_date': 'Fecha y Hora',
            'venue': 'Pabellón',
            'city': 'Ciudad',
            'round_number': 'Jornada',
            'home_score': 'Puntos Local',
            'away_score': 'Puntos Visitante',
            'status': 'Estado',
            'federation_id': 'ID de la Federación',
            'referee1': 'Árbitro 1',
            'referee2': 'Árbitro 2',
            'scorer': 'Anotador',
            'timekeeper': 'Cronometrador',
            'delegate': 'Delegado',
            'field_address': 'Dirección del Campo',
            'federation_club_local_id': 'ID Club Local (Federación)',
            'federation_club_away_id': 'ID Club Visitante (Federación)',
            'acta_html': 'Acta HTML',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar ligas activas
        self.fields['league'].queryset = League.objects.filter(is_active=True)
        # Filtrar equipos activos (esto se actualizará cuando se cree la app teams)
        # self.fields['home_team'].queryset = Team.objects.filter(is_active=True)
        # self.fields['away_team'].queryset = Team.objects.filter(is_active=True)


class FriendlyMatchForm(forms.ModelForm):
    """Formulario específico para partidos amistosos"""
    class Meta:
        model = Match
        fields = [
            'home_team_text', 'away_team_text', 'match_date', 'venue', 'city',
            'home_score', 'away_score', 'referee1', 'referee2', 'field_address'
        ]
        widgets = {
            'home_team_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del equipo local',
                'required': True
            }),
            'away_team_text': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del equipo visitante',
                'required': True
            }),
            'match_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'required': True
            }),
            'venue': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del pabellón'
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ciudad'
            }),
            'home_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 0
            }),
            'away_score': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 0
            }),
            'field_address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Dirección completa del campo'
            }),
        }
        labels = {
            'home_team_text': 'Equipo Local',
            'away_team_text': 'Equipo Visitante',
            'match_date': 'Fecha y Hora',
            'venue': 'Pabellón',
            'city': 'Ciudad',
            'home_score': 'Puntos Local',
            'away_score': 'Puntos Visitante',
            'referee1': 'Árbitro 1',
            'referee2': 'Árbitro 2',
            'field_address': 'Dirección del Campo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Establecer valores por defecto para partidos amistosos
        self.fields['is_friendly'].initial = True
        self.fields['status'].initial = 'scheduled'
        self.fields['round_number'].initial = 1


class ScrapingEndpointForm(forms.ModelForm):
    """Formulario para crear/editar endpoints de scraping"""
    class Meta:
        model = ScrapingEndpoint
        fields = ['league', 'endpoint_type', 'url_pattern', 'parser_type', 'is_active', 'extra_params']
        widgets = {
            'url_pattern': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Usar {league_id}, {round}, etc. para parámetros dinámicos'
            }),
            'extra_params': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Parámetros adicionales como JSON'
            }),
        }
        labels = {
            'league': 'Liga',
            'endpoint_type': 'Tipo de Endpoint',
            'url_pattern': 'Patrón de URL',
            'parser_type': 'Tipo de Parser',
            'is_active': 'Activo',
            'extra_params': 'Parámetros Adicionales',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar ligas activas
        self.fields['league'].queryset = League.objects.filter(is_active=True)


class MatchFilterForm(forms.Form):
    """Formulario para filtrar partidos en el calendario"""
    league = forms.ModelChoiceField(
        queryset=League.objects.filter(is_active=True),
        required=False,
        empty_label="Todas las ligas",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    status = forms.ChoiceField(
        choices=[('', 'Todos los estados')] + Match.MATCH_STATES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )