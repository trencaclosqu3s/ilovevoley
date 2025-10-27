"""
Forms para la gestión de plantillas y personas.
Migrados desde videos.forms para la nueva app rosters.
"""
from django import forms
from django.db.models import Q
from .models import Person, PlayerRole, StaffRole

# Importar modelos de otras apps
from videosvoley.teams.models import Team


class PersonForm(forms.ModelForm):
    """Formulario para crear/editar personas"""
    
    class Meta:
        model = Person
        fields = ['first_name', 'last_name', 'email', 'phone', 'birth_date', 'notes']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Apellidos'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'email@ejemplo.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Teléfono'
            }),
            'birth_date': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'type': 'date'
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
            'email': 'Email',
            'phone': 'Teléfono',
            'birth_date': 'Fecha de Nacimiento',
            'notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hacer campos opcionales
        self.fields['email'].required = False
        self.fields['phone'].required = False
        self.fields['birth_date'].required = False
        self.fields['notes'].required = False

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        email = cleaned_data.get('email')
        
        # Validar que no exista otra persona con el mismo nombre y apellido
        if first_name and last_name:
            existing_person = Person.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_person.exists():
                raise forms.ValidationError(
                    f'Ya existe una persona llamada "{first_name} {last_name}"'
                )
        
        # Validar email único si se proporciona
        if email:
            existing_person = Person.objects.filter(
                email__iexact=email
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_person.exists():
                raise forms.ValidationError(
                    f'Ya existe una persona con el email "{email}"'
                )
        
        return cleaned_data


class PlayerRoleForm(forms.ModelForm):
    """Formulario para crear/editar roles de jugador"""
    
    class Meta:
        model = PlayerRole
        fields = ['team', 'position', 'jersey_number', 'is_active', 'notes']
        widgets = {
            'team': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'position': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Posición (ej: Colocador, Central, etc.)'
            }),
            'jersey_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': '1',
                'max': '99',
                'placeholder': 'Número de camiseta'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 2,
                'placeholder': 'Notas adicionales'
            }),
        }
        labels = {
            'team': 'Equipo',
            'position': 'Posición',
            'jersey_number': 'Número de Camiseta',
            'is_active': 'Activo',
            'notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar queryset de equipos activos
        self.fields['team'].queryset = Team.objects.filter(is_active=True).order_by('name')
        
        # Hacer campos opcionales
        self.fields['position'].required = False
        self.fields['jersey_number'].required = False
        self.fields['notes'].required = False

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        team = cleaned_data.get('team')
        jersey_number = cleaned_data.get('jersey_number')
        
        # Validar que no exista otro jugador con el mismo número en el mismo equipo
        if team and jersey_number:
            existing_role = PlayerRole.objects.filter(
                team=team,
                jersey_number=jersey_number
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_role.exists():
                raise forms.ValidationError(
                    f'Ya existe un jugador con el número {jersey_number} en el equipo {team.name}'
                )
        
        return cleaned_data


class StaffRoleForm(forms.ModelForm):
    """Formulario para crear/editar roles de staff"""
    
    class Meta:
        model = StaffRole
        fields = ['team', 'role', 'is_active', 'notes']
        widgets = {
            'team': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'role': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Rol (ej: Entrenador, Fisioterapeuta, etc.)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 2,
                'placeholder': 'Notas adicionales'
            }),
        }
        labels = {
            'team': 'Equipo',
            'role': 'Rol',
            'is_active': 'Activo',
            'notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar queryset de equipos activos
        self.fields['team'].queryset = Team.objects.filter(is_active=True).order_by('name')
        
        # Hacer campos opcionales
        self.fields['role'].required = False
        self.fields['notes'].required = False


class PersonSearchForm(forms.Form):
    """Formulario de búsqueda de personas"""
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar personas...'
        })
    )
    
    role = forms.ChoiceField(
        choices=[
            ('', 'Todos los roles'),
            ('player', 'Solo jugadores'),
            ('staff', 'Solo staff'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    team = forms.ModelChoiceField(
        queryset=Team.objects.filter(is_active=True),
        required=False,
        empty_label='Todos los equipos',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )


class PersonFilterForm(forms.Form):
    """Formulario de filtros para personas"""
    role = forms.ChoiceField(
        choices=[
            ('', 'Todos los roles'),
            ('player', 'Solo jugadores'),
            ('staff', 'Solo staff'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_role_filter'
        })
    )
    
    team = forms.ModelChoiceField(
        queryset=Team.objects.filter(is_active=True),
        required=False,
        empty_label='Todos los equipos',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_team_filter'
        })
    )
    
    show_all = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2',
            'id': 'id_show_all'
        })
    )


class QuickPersonForm(forms.Form):
    """Formulario rápido para crear personas desde AJAX"""
    first_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Nombre'
        })
    )
    
    last_name = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Apellidos'
        })
    )
    
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'email@ejemplo.com'
        })
    )
    
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Teléfono'
        })
    )