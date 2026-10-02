from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.mixins import get_club_team_names
from ilovevoley.core.models import Season
from ilovevoley.teams.models import Team
from .models import Person, PlayerRole, StaffRole


class PersonForm(forms.ModelForm):
    """Formulario para crear y editar personas del club"""
    
    class Meta:
        model = Person
        fields = ['first_name', 'last_name', 'birth_date', 'photo', 'email', 'phone', 'notes']
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
        }
        labels = {
            'first_name': _('Nombre'),
            'last_name': _('Apellidos'),
            'birth_date': _('Fecha de Nacimiento'),
            'photo': _('Foto'),
            'email': _('Email de Contacto'),
            'phone': _('Teléfono'),
            'notes': _('Algo que quieras que sepamos'),
        }
        help_texts = {
            'birth_date': _('Fecha de nacimiento (opcional)'),
            'photo': _('Foto de perfil (opcional, formatos: JPG, PNG, WebP)'),
            'email': _('Email de contacto (opcional)'),
            'phone': _('Número de teléfono de contacto (opcional)'),
            'notes': _('Información adicional que consideres relevante (opcional)'),
        }
    
    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        # La organización no se expone en el formulario, pero la identidad es
        # por tenant: se fija en la instancia antes de validar para que el
        # UniqueConstraint se compruebe contra el club correcto y no globalmente.
        if organization is not None:
            self.instance.organization = organization
        # Hacer campos opcionales
        self.fields['birth_date'].required = False
        self.fields['photo'].required = False
        self.fields['email'].required = False
        self.fields['phone'].required = False
        self.fields['notes'].required = False

    def _get_validation_exclusions(self):
        # `organization` no es un campo del formulario; sin esto quedaría
        # excluido y el UniqueConstraint (que ahora lo incluye) no se validaría.
        exclude = super()._get_validation_exclusions()
        exclude.discard('organization')
        return exclude

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
    
    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),  # Se configurará en __init__
        label=_('Equipo'),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = PlayerRole
        fields = ['team', 'season', 'jersey_number', 'position', 'notes']
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
            'team': _('Equipo'),
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

        # Filtrar equipos del club
        club_names = get_club_team_names(self.organization)
        # Usar la primera categoría de equipo como filtro principal
        team_query = Q()
        for club_name in club_names:
            team_query |= Q(name__icontains=club_name)

        self.fields['team'].queryset = Team.objects.filter(
            team_query,
            is_active=True
        ).select_related('category').order_by('category__name', 'name')

        # Si hay persona, excluir equipos donde ya tiene rol activo en esa temporada
        if self.person:
            season = self.instance.season if self.instance.pk else self.fields['season'].initial
            active_roles = self.person.player_roles.filter(is_active=True)
            if self.instance.pk:
                active_roles = active_roles.exclude(pk=self.instance.pk)
            if season:
                active_roles = active_roles.filter(season=season)
            self.fields['team'].queryset = self.fields['team'].queryset.exclude(
                id__in=active_roles.values_list('team_id', flat=True)
            )

    def clean(self):
        # Red de seguridad ante envíos manipulados: el queryset ya excluye el
        # equipo, pero el constraint de BD no debe convertirse en un 500.
        cleaned = super().clean()
        team = cleaned.get('team')
        season = cleaned.get('season')
        if self.person and team and season:
            existing = PlayerRole.objects.filter(
                person=self.person, team=team, season=season, is_active=True
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
    
    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),  # Se configurará en __init__
        label=_('Equipo'),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = StaffRole
        fields = ['team', 'season', 'role', 'notes']
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
            'team': _('Equipo'),
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

        # Filtrar equipos del club
        club_names = get_club_team_names(self.organization)
        team_query = Q()
        for club_name in club_names:
            team_query |= Q(name__icontains=club_name)

        self.fields['team'].queryset = Team.objects.filter(
            team_query,
            is_active=True
        ).select_related('category').order_by('category__name', 'name')

        # Una persona puede tener varios roles distintos en el mismo equipo y
        # temporada (p.ej. entrenador y delegado); lo valida el UniqueConstraint
        # (person, team, role, season), no el queryset.

    def clean(self):
        cleaned = super().clean()
        team = cleaned.get('team')
        role = cleaned.get('role')
        season = cleaned.get('season')
        if self.person and team and role and season:
            existing = StaffRole.objects.filter(
                person=self.person, team=team, role=role, season=season, is_active=True
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    _('Esta persona ya tiene ese rol en este equipo y temporada.')
                )
        return cleaned


__all__ = [
    'PersonForm',
    'PlayerRoleForm',
    'StaffRoleForm',
]
