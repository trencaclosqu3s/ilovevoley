from django import forms
from django.utils import timezone

from ilovevoley.core.models import Category, Season
from ilovevoley.teams.models import Club, Team
from .models import League, Match


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
            league_category = self.instance.league.categories.first()  # Usar la primera categoría

            # Verificar si se envió el formulario con el checkbox
            if self.data and 'filter_by_category' in self.data:
                filter_by_category = self.data.get('filter_by_category') == 'on'

        # Si hay datos POST sobre league, obtener la categoría de esa liga
        elif self.data and 'league' in self.data and self.data['league']:
            try:
                league = League.objects.get(id=self.data['league'])
                league_category = league.categories.first()  # Usar la primera categoría
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

    # Campo de búsqueda para equipo local (con autocompletado)
    home_team_search = forms.CharField(
        required=False,
        label='Equipo Local (buscar)',
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Busca un equipo existente o escribe el nombre...',
            'id': 'id_home_team_search',
            'autocomplete': 'off'
        }),
        help_text='Comienza a escribir para buscar equipos existentes'
    )

    # Campo oculto para el ID del equipo local seleccionado
    home_team_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_home_team_id'})
    )

    # Campo de búsqueda para equipo visitante (con autocompletado)
    away_team_search = forms.CharField(
        required=False,
        label='Equipo Visitante (buscar)',
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Busca un equipo existente o escribe el nombre...',
            'id': 'id_away_team_search',
            'autocomplete': 'off'
        }),
        help_text='Comienza a escribir para buscar equipos existentes'
    )

    # Campo oculto para el ID del equipo visitante seleccionado
    away_team_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_away_team_id'})
    )

    # Campos para registrar equipos nuevos
    register_home_team = forms.BooleanField(
        required=False,
        label='Registrar equipo local para futuros partidos',
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-csj-purple focus:ring-csj-purple',
            'id': 'id_register_home_team'
        })
    )

    home_team_club = forms.ModelChoiceField(
        required=False,
        queryset=None,  # Se configurará en __init__
        label='Club del equipo local',
        empty_label='Seleccionar club (opcional)',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_home_team_club'
        })
    )

    register_away_team = forms.BooleanField(
        required=False,
        label='Registrar equipo visitante para futuros partidos',
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-csj-purple focus:ring-csj-purple',
            'id': 'id_register_away_team'
        })
    )

    away_team_club = forms.ModelChoiceField(
        required=False,
        queryset=None,  # Se configurará en __init__
        label='Club del equipo visitante',
        empty_label='Seleccionar club (opcional)',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_away_team_club'
        })
    )

    class Meta:
        model = Match
        fields = ['match_date', 'venue', 'city']
        widgets = {
            'match_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            }),
            'venue': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ej: Polideportivo Municipal'
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ej: Palma'
            }),
        }
        labels = {
            'match_date': 'Fecha y Hora',
            'venue': 'Instalación',
            'city': 'Ciudad',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['venue'].required = False
        self.fields['city'].required = False

        # Configurar querysets para clubs
        self.fields['home_team_club'].queryset = Club.objects.all().order_by('official_name')
        self.fields['away_team_club'].queryset = Club.objects.all().order_by('official_name')

        # Pre-rellenar campos de búsqueda si estamos editando
        if self.instance and self.instance.pk:
            if self.instance.home_team:
                self.fields['home_team_search'].initial = self.instance.home_team.name
                self.fields['home_team_id'].initial = self.instance.home_team.id
                if self.instance.home_team.club:
                    self.fields['home_team_club'].initial = self.instance.home_team.club
            elif self.instance.home_team_text:
                self.fields['home_team_search'].initial = self.instance.home_team_text

            if self.instance.away_team:
                self.fields['away_team_search'].initial = self.instance.away_team.name
                self.fields['away_team_id'].initial = self.instance.away_team.id
                if self.instance.away_team.club:
                    self.fields['away_team_club'].initial = self.instance.away_team.club
            elif self.instance.away_team_text:
                self.fields['away_team_search'].initial = self.instance.away_team_text

    def clean(self):
        cleaned_data = super().clean()

        # Validar equipo local
        home_team_id = cleaned_data.get('home_team_id')
        home_team_search = cleaned_data.get('home_team_search')

        # Si home_team_search es None o vacío, el campo está vacío
        if home_team_search:
            home_team_search = home_team_search.strip()

        if not home_team_id and not home_team_search:
            raise forms.ValidationError('Debes especificar un equipo local')

        # Validar equipo visitante
        away_team_id = cleaned_data.get('away_team_id')
        away_team_search = cleaned_data.get('away_team_search')

        # Si away_team_search es None o vacío, el campo está vacío
        if away_team_search:
            away_team_search = away_team_search.strip()

        if not away_team_id and not away_team_search:
            raise forms.ValidationError('Debes especificar un equipo visitante')

        # Guardar los valores procesados en cleaned_data
        cleaned_data['home_team_search'] = home_team_search or ''
        cleaned_data['away_team_search'] = away_team_search or ''

        return cleaned_data

    def save(self, commit=True):
        # No llamar a super().save() todavía porque necesitamos configurar los campos primero
        # para evitar que la validación del modelo falle

        # Obtener la instancia pero sin validar todavía
        instance = Match()

        # Copiar campos del formulario
        instance.match_date = self.cleaned_data.get('match_date')
        instance.venue = self.cleaned_data.get('venue', '')
        instance.city = self.cleaned_data.get('city', '')

        # Marcar como amistoso
        instance.is_friendly = True
        instance.status = 'scheduled'
        instance.federation_id = None  # Los amistosos no tienen federation_id
        instance.round_number = 1  # Por defecto

        # Obtener categoría seleccionada
        category = self.cleaned_data.get('category')

        # Procesar equipo local
        home_team_id = self.cleaned_data.get('home_team_id')
        home_team_search = self.cleaned_data.get('home_team_search', '').strip()
        register_home_team = self.cleaned_data.get('register_home_team', False)
        home_team_club = self.cleaned_data.get('home_team_club')

        if home_team_id:
            # Equipo existente seleccionado
            try:
                instance.home_team = Team.objects.get(id=home_team_id)
                instance.home_team_text = ''
            except Team.DoesNotExist:
                instance.home_team = None
                instance.home_team_text = home_team_search
        else:
            # Texto libre - verificar si hay que registrar como nuevo equipo
            if register_home_team and home_team_search and category:
                # Crear nuevo equipo
                new_team = Team.objects.create(
                    name=home_team_search,
                    category=category,
                    club=home_team_club,
                    is_active=True
                )
                instance.home_team = new_team
                instance.home_team_text = ''
            else:
                # Solo texto libre
                instance.home_team = None
                instance.home_team_text = home_team_search

        # Procesar equipo visitante
        away_team_id = self.cleaned_data.get('away_team_id')
        away_team_search = self.cleaned_data.get('away_team_search', '').strip()
        register_away_team = self.cleaned_data.get('register_away_team', False)
        away_team_club = self.cleaned_data.get('away_team_club')

        if away_team_id:
            # Equipo existente seleccionado
            try:
                instance.away_team = Team.objects.get(id=away_team_id)
                instance.away_team_text = ''
            except Team.DoesNotExist:
                instance.away_team = None
                instance.away_team_text = away_team_search
        else:
            # Texto libre - verificar si hay que registrar como nuevo equipo
            if register_away_team and away_team_search and category:
                # Crear nuevo equipo
                new_team = Team.objects.create(
                    name=away_team_search,
                    category=category,
                    club=away_team_club,
                    is_active=True
                )
                instance.away_team = new_team
                instance.away_team_text = ''
            else:
                # Solo texto libre
                instance.away_team = None
                instance.away_team_text = away_team_search

        # Crear o buscar liga de amistosos para esta categoría
        if category:
            current_season = Season.objects.for_date(timezone.now())

            # Buscar o crear liga de amistosos
            league, created = League.objects.get_or_create(
                federation_id=f"friendly-{category.id}-{current_season.name}",
                defaults={
                    'name': f"Amistosos - {category.name}",
                    'season': current_season,
                    'competition_type': 'friendly',
                    'is_active': True,
                }
            )
            if created or not league.categories.filter(id=category.id).exists():
                league.categories.add(category)
            instance.league = league

        if commit:
            instance.save()

        return instance


class MatchResultForm(forms.ModelForm):
    """Formulario simple para agregar resultado de partido"""

    class Meta:
        model = Match
        fields = ['home_score', 'away_score']
        widgets = {
            'home_score': forms.NumberInput(attrs={
                'class': 'w-20 px-3 py-2 border border-gray-300 rounded-lg text-center text-lg font-semibold',
                'min': '0',
                'max': '99',
                'placeholder': '0'
            }),
            'away_score': forms.NumberInput(attrs={
                'class': 'w-20 px-3 py-2 border border-gray-300 rounded-lg text-center text-lg font-semibold',
                'min': '0',
                'max': '99',
                'placeholder': '0'
            }),
        }
        labels = {
            'home_score': 'Local',
            'away_score': 'Visitante',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['home_score'].required = True
        self.fields['away_score'].required = True

    def clean(self):
        cleaned_data = super().clean()
        home_score = cleaned_data.get('home_score')
        away_score = cleaned_data.get('away_score')

        if home_score is not None and away_score is not None:
            if home_score < 0 or away_score < 0:
                raise forms.ValidationError('Los marcadores no pueden ser negativos.')

            if home_score == away_score:
                raise forms.ValidationError('En voleibol no puede haber empate. Revisa los marcadores.')

        return cleaned_data

    def save(self, commit=True):
        match = super().save(commit=False)
        match.status = 'finished'
        if commit:
            match.save()
        return match


__all__ = [
    'MatchAdminForm',
    'FriendlyMatchForm',
    'MatchResultForm',
]
