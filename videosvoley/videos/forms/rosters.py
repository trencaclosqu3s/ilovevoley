from django import forms
from django.db.models import Q

from videosvoley.core.mixins import get_club_team_names
from ..models import Category, Person, PlayerRole, StaffRole, Team


class PersonForm(forms.ModelForm):
    """Formulario para crear y editar personas del club"""
    
    class Meta:
        model = Person
        fields = ['first_name', 'last_name', 'birth_date', 'photo', 'email', 'phone', 'notes']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': 'Ej: María'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': 'Ej: García López'
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
                'placeholder': 'Algo que quieras que sepamos sobre esta persona...'
            }),
        }
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellidos',
            'birth_date': 'Fecha de Nacimiento',
            'photo': 'Foto',
            'email': 'Email de Contacto',
            'phone': 'Teléfono',
            'notes': 'Algo que quieras que sepamos',
        }
        help_texts = {
            'birth_date': 'Fecha de nacimiento (opcional)',
            'photo': 'Foto de perfil (opcional, formatos: JPG, PNG, WebP)',
            'email': 'Email de contacto (opcional)',
            'phone': 'Número de teléfono de contacto (opcional)',
            'notes': 'Información adicional que consideres relevante (opcional)',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer campos opcionales
        self.fields['birth_date'].required = False
        self.fields['photo'].required = False
        self.fields['email'].required = False
        self.fields['phone'].required = False
        self.fields['notes'].required = False
    
    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            # Validar tamaño (5MB máximo)
            if photo.size > 5 * 1024 * 1024:
                raise forms.ValidationError('El archivo es demasiado grande. Tamaño máximo: 5MB')
            
            # Validar tipo de archivo
            if not photo.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                raise forms.ValidationError('Formato no válido. Use JPG, PNG o WebP')
        
        return photo


class PlayerRoleForm(forms.ModelForm):
    """Formulario para crear y editar roles de jugador"""
    
    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),  # Se configurará en __init__
        label='Equipo',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = PlayerRole
        fields = ['team', 'jersey_number', 'position', 'notes']
        widgets = {
            'jersey_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'placeholder': 'Ej: 10',
                'min': '1',
                'max': '99'
            }),
            'position': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': 'Notas sobre este rol en el equipo'
            }),
        }
        labels = {
            'team': 'Equipo',
            'jersey_number': 'Número de Dorsal',
            'position': 'Posición Principal',
            'notes': 'Notas',
        }
        help_texts = {
            'jersey_number': 'Número de camiseta (opcional)',
            'position': 'Posición preferida del jugador (opcional)',
            'notes': 'Información adicional sobre este rol (opcional)',
        }
    
    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        person = kwargs.pop('person', None)
        super().__init__(*args, **kwargs)

        # Hacer campos opcionales
        self.fields['jersey_number'].required = False
        self.fields['position'].required = False
        self.fields['notes'].required = False

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

        # Si hay persona, excluir equipos donde ya tiene rol activo
        if person:
            active_team_ids = person.player_roles.filter(is_active=True).values_list('team_id', flat=True)
            self.fields['team'].queryset = self.fields['team'].queryset.exclude(id__in=active_team_ids)


class StaffRoleForm(forms.ModelForm):
    """Formulario para crear y editar roles de staff"""
    
    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),  # Se configurará en __init__
        label='Equipo',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
        })
    )
    
    class Meta:
        model = StaffRole
        fields = ['team', 'role', 'notes']
        widgets = {
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': 'Notas sobre este rol en el equipo'
            }),
        }
        labels = {
            'team': 'Equipo',
            'role': 'Rol en el Equipo',
            'notes': 'Notas',
        }
        help_texts = {
            'role': 'Función que desempeña en el equipo',
            'notes': 'Información adicional sobre este rol (opcional)',
        }
    
    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        person = kwargs.pop('person', None)
        super().__init__(*args, **kwargs)

        # Hacer campo notes opcional
        self.fields['notes'].required = False

        # Filtrar equipos del club
        club_names = get_club_team_names(self.organization)
        team_query = Q()
        for club_name in club_names:
            team_query |= Q(name__icontains=club_name)

        self.fields['team'].queryset = Team.objects.filter(
            team_query,
            is_active=True
        ).select_related('category').order_by('category__name', 'name')

        # Si hay persona, excluir combinaciones equipo-rol donde ya tiene rol activo
        if person:
            # No se puede tener el mismo rol en el mismo equipo
            active_roles = person.staff_roles.filter(is_active=True).values_list('team_id', 'role')
            # Esto se validará en el clean del formulario


__all__ = [
    'PersonForm',
    'PlayerRoleForm',
    'StaffRoleForm',
]
