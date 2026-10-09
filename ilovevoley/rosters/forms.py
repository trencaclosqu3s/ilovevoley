from datetime import date

from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.mixins import get_club_team_names
from ilovevoley.core.models import Season
from ilovevoley.teams.models import Team, TeamIdentity
from .models import Person, PlayerRole, StaffRole


def _club_teams_for_seasons(organization, seasons):
    """Equipos activos del club con presencia en alguna de ``seasons``.

    Presencia = clasificación, partido o rol de plantilla en esa temporada. Hay una
    fila de ``Team`` por fase federativa, así que sin este filtro el selector
    ofrece equipos de otros años con el mismo nombre.
    """
    name_query = Q()
    for club_name in get_club_team_names(organization):
        name_query |= Q(name__icontains=club_name)
    in_season = (
        Q(standings__league__season__in=seasons)
        | Q(home_matches__league__season__in=seasons)
        | Q(away_matches__league__season__in=seasons)
        | Q(identity__player_roles__season__in=seasons)
        | Q(identity__staff_roles__season__in=seasons)
    )
    teams = Team.objects.filter(name_query, is_active=True).select_related('category').order_by('category__name', 'name')
    in_season_teams = teams.filter(in_season).distinct()
    # Temporada recién creada y sin scrapear (#344): ninguna fila tiene presencia
    # todavía, así que se ofrecen todos los equipos del club.
    return in_season_teams if in_season_teams.exists() else teams


def _club_identities_for_seasons(organization, seasons):
    """Identidades de los equipos de ``_club_teams_for_seasons``: una opción por
    equipo aunque juegue varias fases. Un equipo sin identidad no puede tener
    plantilla (#447)."""
    teams = _club_teams_for_seasons(organization, seasons)
    return (
        TeamIdentity.objects.filter(pk__in=teams.values('identity'))
        .select_related('category')
        .order_by('category__name', 'core_name')
    )


class IdentityChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.core_name} · {obj.category}' if obj.category_id else obj.core_name


def _form_seasons(form):
    """Temporadas cuyos equipos debe ofrecer el selector: la de partida y la enviada."""
    season = form.instance.season if form.instance.pk else form.fields['season'].initial
    seasons = [season] if season else []
    if form.is_bound:
        try:
            seasons.append(Season.objects.get(pk=form.data.get('season')))
        except (Season.DoesNotExist, ValueError):
            pass
    return seasons


class PersonForm(forms.ModelForm):
    """Formulario para crear y editar personas del club"""
    
    class Meta:
        model = Person
        fields = ['first_name', 'last_name', 'birth_date', 'birth_year', 'photo', 'email', 'phone', 'notes', 'image_consent']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': _('Ej: María')
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': _('Ej: García López')
            }),
            'birth_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
            }, format='%Y-%m-%d'),
            'birth_year': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': _('Ej: 2012'),
            }),
            'photo': forms.FileInput(attrs={
                'class': 'hidden',
                'id': 'person-photo-input',
                'accept': 'image/jpeg,image/jpg,image/png,image/webp',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': 'email@ejemplo.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': '+34 600 000 000'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'rows': 3,
                'placeholder': _('Algo que quieras que sepamos sobre esta persona...')
            }),
            'image_consent': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
            }),
        }
        labels = {
            'first_name': _('Nombre'),
            'last_name': _('Apellidos'),
            'birth_date': _('Fecha de Nacimiento'),
            'birth_year': _('Año de Nacimiento'),
            'photo': _('Foto'),
            'email': _('Email de Contacto'),
            'phone': _('Teléfono'),
            'notes': _('Algo que quieras que sepamos'),
        }
        help_texts = {
            'birth_date': _('Fecha de nacimiento (opcional)'),
            'birth_year': _('Obligatorio si no indicas la fecha de nacimiento completa'),
            'photo': _('Foto de perfil (opcional, formatos: JPG, PNG, WebP)'),
            'email': _('Email de contacto (opcional)'),
            'phone': _('Número de teléfono de contacto (opcional)'),
            'notes': _('Información adicional que consideres relevante (opcional)'),
            'image_consent': _('Si eliges "Sin consentimiento", se avisará a quien etiquete o modere fotos en las que aparezca.'),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer campos opcionales
        self.fields['birth_date'].required = False
        # El año se exige en clean(): lo deduce la fecha si se indica
        self.fields['birth_year'].required = False
        self.fields['photo'].required = False
        self.fields['email'].required = False
        self.fields['phone'].required = False
        self.fields['notes'].required = False
        # El alta rápida no envía el campo: se conserva el valor de la ficha.
        self.fields['image_consent'].required = False

    def clean_image_consent(self):
        return self.cleaned_data.get('image_consent') or self.instance.image_consent

    def clean(self):
        cleaned = super().clean()
        birth_date = cleaned.get('birth_date')
        if birth_date:
            cleaned['birth_year'] = birth_date.year
        elif not cleaned.get('birth_year') and 'birth_year' not in self.errors:
            self.add_error('birth_year', _('Indica el año de nacimiento o la fecha completa.'))
        return cleaned

    def clean_birth_year(self):
        year = self.cleaned_data.get('birth_year')
        if year is not None and not 1900 <= year <= date.today().year:
            raise forms.ValidationError(_('Año de nacimiento no válido.'))
        return year

    def existing_person(self):
        """Ficha global con la misma identidad (otra distinta de esta), si existe."""
        data = self.cleaned_data
        if not (data.get('first_name') and data.get('last_name') and data.get('birth_year')):
            return None
        return Person._base_manager.filter(
            first_name=data['first_name'], last_name=data['last_name'],
            birth_year=data['birth_year'],
        ).exclude(pk=self.instance.pk).first()

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            # Validar tamaño (5MB máximo)
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError(_('El archivo es demasiado grande. Tamaño máximo: 5MB'))
            
            # Validar tipo de archivo
            if not photo.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                raise forms.ValidationError(_('Formato no válido. Use JPG, PNG o WebP'))

        return photo


class PlayerRoleForm(forms.ModelForm):
    """Formulario para crear y editar roles de jugador"""
    
    identity = IdentityChoiceField(
        queryset=TeamIdentity.objects.none(),  # Se configurará en __init__
        label=_('Equipo'),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = PlayerRole
        fields = ['identity', 'season', 'jersey_number', 'position', 'notes']
        widgets = {
            'season': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
            }),
            'jersey_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': _('Ej: 10'),
                'min': '1',
                'max': '99'
            }),
            'position': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': _('Notas sobre este rol en el equipo')
            }),
        }
        labels = {
            'identity': _('Equipo'),
            'season': _('Temporada'),
            'jersey_number': _('Número de Dorsal'),
            'position': _('Posición Principal'),
            'notes': _('Notas'),
        }
        help_texts = {
            'season': _('Temporada en la que el jugador pertenece al equipo'),
            'jersey_number': _('Número de camiseta (opcional)'),
            'position': _('Posición preferida del jugador (opcional)'),
            'notes': _('Información adicional sobre este rol (opcional)'),
        }
    
    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        self.person = kwargs.pop('person', None)
        super().__init__(*args, **kwargs)

        # Hacer campos opcionales
        self.fields['jersey_number'].required = False
        self.fields['position'].required = False
        self.fields['notes'].required = False

        # Temporada obligatoria; por defecto, la activa
        self.fields['season'].required = True
        if not self.instance.pk:
            self.fields['season'].initial = Season.objects.current()

        # Equipos del club con presencia en la temporada
        self.fields['identity'].queryset = _club_identities_for_seasons(self.organization, _form_seasons(self))

        # Si hay persona, excluir equipos donde ya tiene rol activo en esa temporada
        if self.person:
            season = self.instance.season if self.instance.pk else self.fields['season'].initial
            active_roles = self.person.player_roles.filter(is_active=True)
            if self.instance.pk:
                active_roles = active_roles.exclude(pk=self.instance.pk)
            if season:
                active_roles = active_roles.filter(season=season)
            self.fields['identity'].queryset = self.fields['identity'].queryset.exclude(
                id__in=active_roles.values_list('identity_id', flat=True)
            )

    def clean(self):
        # Red de seguridad ante envíos manipulados: el queryset ya excluye el
        # equipo, pero el constraint de BD no debe convertirse en un 500.
        cleaned = super().clean()
        identity = cleaned.get('identity')
        season = cleaned.get('season')
        if self.person and identity and season:
            existing = PlayerRole.objects.filter(
                person=self.person, identity=identity, season=season, is_active=True
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    _('Esta persona ya tiene un rol de jugador en este equipo y temporada.')
                )
        return cleaned


class StaffRoleForm(forms.ModelForm):
    """Formulario para crear y editar roles de staff"""
    
    identity = IdentityChoiceField(
        queryset=TeamIdentity.objects.none(),  # Se configurará en __init__
        label=_('Equipo'),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = StaffRole
        fields = ['identity', 'season', 'role', 'notes']
        widgets = {
            'season': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': _('Notas sobre este rol en el equipo')
            }),
        }
        labels = {
            'identity': _('Equipo'),
            'season': _('Temporada'),
            'role': _('Rol en el Equipo'),
            'notes': _('Notas'),
        }
        help_texts = {
            'season': _('Temporada en la que la persona desempeña el rol'),
            'role': _('Función que desempeña en el equipo'),
            'notes': _('Información adicional sobre este rol (opcional)'),
        }
    
    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        self.person = kwargs.pop('person', None)
        super().__init__(*args, **kwargs)

        # Hacer campo notes opcional
        self.fields['notes'].required = False

        # Temporada obligatoria; por defecto, la activa
        self.fields['season'].required = True
        if not self.instance.pk:
            self.fields['season'].initial = Season.objects.current()

        # Equipos del club con presencia en la temporada
        self.fields['identity'].queryset = _club_identities_for_seasons(self.organization, _form_seasons(self))

        # Una persona puede tener varios roles distintos en el mismo equipo y
        # temporada (p.ej. entrenador y delegado); lo valida el UniqueConstraint
        # (person, identity, role, season), no el queryset.

    def clean(self):
        cleaned = super().clean()
        identity = cleaned.get('identity')
        role = cleaned.get('role')
        season = cleaned.get('season')
        if self.person and identity and role and season:
            existing = StaffRole.objects.filter(
                person=self.person, identity=identity, role=role, season=season, is_active=True
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    _('Esta persona ya tiene ese rol en este equipo y temporada.')
                )
        return cleaned


class BulkPlayerRosterForm:
    """Alta masiva de jugadores en un equipo y temporada (#446).

    No es un ``forms.Form``: cada candidata es una fila (casilla + dorsal +
    posición) y el error es por fila, no por campo. ``initial`` precarga filas
    marcadas con ``{person_id: (jersey_number, position)}``.
    """

    def __init__(self, team, season, candidates, data=None, initial=None):
        self.team = team
        self.season = season
        self.is_bound = data is not None
        self.errors = []
        self.rows = []
        initial = initial or {}
        for person in candidates:
            pid = str(person.pk)
            if self.is_bound:
                checked = pid in data.getlist('selected')
                jersey = data.get(f'jersey_{pid}', '').strip()
                position = data.get(f'position_{pid}', '')
            else:
                checked = person.pk in initial
                jersey, position = initial.get(person.pk, ('', ''))
                jersey = '' if jersey is None else str(jersey)
            self.rows.append({
                'person': person, 'checked': checked, 'jersey': jersey,
                'position': position, 'error': '',
            })

    @property
    def positions(self):
        return PlayerRole.POSITION_CHOICES

    def is_valid(self):
        selected = [row for row in self.rows if row['checked']]
        if not selected:
            self.errors.append(_('Selecciona al menos un jugador.'))
            return False
        # El constraint solo cubre dorsales con rol activo en ese equipo y temporada.
        taken = set(
            PlayerRole.objects.filter(
                identity=self.team.identity, season=self.season, is_active=True, jersey_number__isnull=False,
            ).values_list('jersey_number', flat=True)
        )
        valid_positions = {key for key, _label in PlayerRole.POSITION_CHOICES}
        seen = set()
        for row in selected:
            number = None
            if row['jersey']:
                if not (row['jersey'].isascii() and row['jersey'].isdigit() and 1 <= int(row['jersey']) <= 99):
                    row['error'] = _('El dorsal debe estar entre 1 y 99.')
                    continue
                number = int(row['jersey'])
                if number in taken:
                    row['error'] = _('El dorsal %(n)s ya está en uso en este equipo.') % {'n': number}
                    continue
                if number in seen:
                    row['error'] = _('El dorsal %(n)s está repetido en este alta.') % {'n': number}
                    continue
                seen.add(number)
            if row['position'] and row['position'] not in valid_positions:
                row['error'] = _('Posición no válida.')
        return not any(row['error'] for row in selected)

    def save(self):
        """Crea todos los roles o ninguno; devuelve cuántos."""
        roles = [
            PlayerRole(
                person=row['person'], identity=self.team.identity, season=self.season,
                jersey_number=int(row['jersey']) if row['jersey'] else None,
                position=row['position'],
            )
            for row in self.rows if row['checked']
        ]
        with transaction.atomic():
            PlayerRole.objects.bulk_create(roles)
        return len(roles)


__all__ = [
    'PersonForm',
    'PlayerRoleForm',
    'BulkPlayerRosterForm',
    'StaffRoleForm',
]
