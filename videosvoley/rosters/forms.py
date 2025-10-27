from django import forms
from django.core.exceptions import ValidationError
from .models import Person, PlayerRole, StaffRole


class PersonForm(forms.ModelForm):
    """Formulario para crear/editar personas"""
    class Meta:
        model = Person
        fields = [
            'first_name', 'last_name', 'birth_date', 'photo', 'email', 
            'phone', 'user', 'notes', 'is_active'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Apellidos'
            }),
            'birth_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'type': 'date'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'email@ejemplo.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Teléfono'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Notas adicionales'
            }),
        }
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellidos',
            'birth_date': 'Fecha de Nacimiento',
            'photo': 'Foto',
            'email': 'Email',
            'phone': 'Teléfono',
            'user': 'Usuario Vinculado',
            'notes': 'Notas',
            'is_active': 'Activo',
        }

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        birth_date = cleaned_data.get('birth_date')
        
        # Validar que al menos nombre y apellido estén presentes
        if not first_name or not last_name:
            raise ValidationError('Nombre y apellidos son obligatorios.')
        
        # Validar edad mínima (opcional)
        if birth_date:
            from datetime import date
            today = date.today()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            if age < 5:
                raise ValidationError('La edad mínima es 5 años.')
            if age > 100:
                raise ValidationError('La edad máxima es 100 años.')
        
        return cleaned_data


class PlayerRoleForm(forms.ModelForm):
    """Formulario para crear/editar roles de jugador"""
    class Meta:
        model = PlayerRole
        fields = [
            'person', 'team', 'jersey_number', 'position', 
            'is_active', 'notes'
        ]
        widgets = {
            'jersey_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '1',
                'max': '99',
                'placeholder': 'Número de dorsal (1-99)'
            }),
            'position': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 2,
                'placeholder': 'Notas sobre este rol'
            }),
        }
        labels = {
            'person': 'Persona',
            'team': 'Equipo',
            'jersey_number': 'Número de Dorsal',
            'position': 'Posición',
            'is_active': 'Activo',
            'notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar personas activas
        self.fields['person'].queryset = Person.objects.filter(is_active=True).order_by('last_name', 'first_name')
        # Filtrar equipos activos
        self.fields['team'].queryset = self.fields['team'].queryset.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        person = cleaned_data.get('person')
        team = cleaned_data.get('team')
        jersey_number = cleaned_data.get('jersey_number')
        is_active = cleaned_data.get('is_active', True)
        
        # Validar que no haya duplicados de persona-equipo activos
        if person and team and is_active:
            existing = PlayerRole.objects.filter(
                person=person,
                team=team,
                is_active=True
            ).exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError(f'{person.full_name} ya tiene un rol activo en {team.name}.')
        
        # Validar número de dorsal único en el equipo
        if jersey_number and team and is_active:
            existing = PlayerRole.objects.filter(
                team=team,
                jersey_number=jersey_number,
                is_active=True
            ).exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError(f'El número {jersey_number} ya está en uso en {team.name}.')
        
        return cleaned_data


class StaffRoleForm(forms.ModelForm):
    """Formulario para crear/editar roles de staff"""
    class Meta:
        model = StaffRole
        fields = [
            'person', 'team', 'role', 'is_active', 'notes'
        ]
        widgets = {
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 2,
                'placeholder': 'Notas sobre este rol'
            }),
        }
        labels = {
            'person': 'Persona',
            'team': 'Equipo',
            'role': 'Rol',
            'is_active': 'Activo',
            'notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar personas activas
        self.fields['person'].queryset = Person.objects.filter(is_active=True).order_by('last_name', 'first_name')
        # Filtrar equipos activos
        self.fields['team'].queryset = self.fields['team'].queryset.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        person = cleaned_data.get('person')
        team = cleaned_data.get('team')
        role = cleaned_data.get('role')
        is_active = cleaned_data.get('is_active', True)
        
        # Validar que no haya duplicados de persona-equipo-rol activos
        if person and team and role and is_active:
            existing = StaffRole.objects.filter(
                person=person,
                team=team,
                role=role,
                is_active=True
            ).exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise ValidationError(f'{person.full_name} ya tiene el rol de {self.get_role_display()} activo en {team.name}.')
        
        return cleaned_data


class PersonFilterForm(forms.Form):
    """Formulario para filtrar personas"""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar personas...'
        })
    )
    
    role = forms.ChoiceField(
        choices=[
            ('', 'Todos los roles'),
            ('players', 'Solo jugadores'),
            ('staff', 'Solo staff'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    age_min = forms.IntegerField(
        required=False,
        min_value=5,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Edad mínima'
        })
    )
    
    age_max = forms.IntegerField(
        required=False,
        min_value=5,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Edad máxima'
        })
    )
    
    active_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )
    
    has_roles = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        age_min = cleaned_data.get('age_min')
        age_max = cleaned_data.get('age_max')
        
        if age_min and age_max and age_min > age_max:
            raise ValidationError('La edad mínima no puede ser mayor que la edad máxima.')
        
        return cleaned_data


class RosterFilterForm(forms.Form):
    """Formulario para filtrar plantillas"""
    team = forms.ModelChoiceField(
        queryset=None,  # Se establecerá en __init__
        required=False,
        empty_label="Todos los equipos",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    position = forms.ChoiceField(
        choices=[('', 'Todas las posiciones')] + PlayerRole.POSITION_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    role = forms.ChoiceField(
        choices=[('', 'Todos los roles')] + StaffRole.STAFF_ROLES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    active_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Obtener equipos activos
        from videosvoley.videos.models import Team
        self.fields['team'].queryset = Team.objects.filter(is_active=True).order_by('name')


class JerseyNumberForm(forms.Form):
    """Formulario para asignar número de dorsal"""
    jersey_number = forms.IntegerField(
        min_value=1,
        max_value=99,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Número de dorsal (1-99)'
        })
    )
    
    def clean_jersey_number(self):
        jersey_number = self.cleaned_data.get('jersey_number')
        if jersey_number and (jersey_number < 1 or jersey_number > 99):
            raise ValidationError('El número de dorsal debe estar entre 1 y 99.')
        return jersey_number