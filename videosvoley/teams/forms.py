"""
Forms para la gestión de equipos y clubs.
Migrados desde videos.forms para la nueva app teams.
"""
from django import forms
from django.db.models import Q
from .models import Team, Club

# Importar modelos de otras apps
from videosvoley.content.models import Category


class TeamForm(forms.ModelForm):
    """Formulario para crear/editar equipos"""
    
    class Meta:
        model = Team
        fields = ['name', 'category', 'club', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del equipo'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'club': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
            }),
        }
        labels = {
            'name': 'Nombre del Equipo',
            'category': 'Categoría',
            'club': 'Club',
            'is_active': 'Activo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar queryset de categorías activas
        self.fields['category'].queryset = Category.objects.filter(is_active=True).order_by('name')
        
        # Configurar queryset de clubs activos
        self.fields['club'].queryset = Club.objects.all().order_by('official_name')
        
        # Hacer club opcional
        self.fields['club'].required = False

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        category = cleaned_data.get('category')
        
        # Validar que no exista otro equipo con el mismo nombre en la misma categoría
        if name and category:
            existing_team = Team.objects.filter(
                name__iexact=name,
                category=category
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_team.exists():
                raise forms.ValidationError(
                    f'Ya existe un equipo llamado "{name}" en la categoría {category.name}'
                )
        
        return cleaned_data


class ClubForm(forms.ModelForm):
    """Formulario para crear/editar clubs"""
    
    class Meta:
        model = Club
        fields = ['official_name', 'president', 'address', 'phone', 'email', 'venue_name', 'venue_address', 'province', 'instagram', 'facebook', 'twitter', 'website', 'logo_url']
        widgets = {
            'official_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre oficial del club'
            }),
            'president': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Presidente del club'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Dirección del club'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Teléfono'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Email'
            }),
            'venue_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del pabellón'
            }),
            'venue_address': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Dirección del pabellón'
            }),
            'province': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Provincia'
            }),
            'instagram': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Instagram'
            }),
            'facebook': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Facebook'
            }),
            'twitter': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Twitter'
            }),
            'website': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Sitio web'
            }),
            'logo_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'URL del logo'
            }),
        }
        labels = {
            'official_name': 'Nombre Oficial',
            'president': 'Presidente',
            'address': 'Dirección',
            'phone': 'Teléfono',
            'email': 'Email',
            'venue_name': 'Pabellón',
            'venue_address': 'Dirección del Pabellón',
            'province': 'Provincia',
            'instagram': 'Instagram',
            'facebook': 'Facebook',
            'twitter': 'Twitter',
            'website': 'Sitio Web',
            'logo_url': 'Logo URL',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hacer campos opcionales
        self.fields['short_name'].required = False
        self.fields['address'].required = False
        self.fields['phone'].required = False
        self.fields['email'].required = False
        self.fields['website'].required = False

    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        official_name = cleaned_data.get('official_name')
        short_name = cleaned_data.get('short_name')
        
        # Validar que no exista otro club con el mismo nombre oficial
        if official_name:
            existing_club = Club.objects.filter(
                official_name__iexact=official_name
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_club.exists():
                raise forms.ValidationError(
                    f'Ya existe un club con el nombre oficial "{official_name}"'
                )
        
        # Validar que no exista otro club con el mismo nombre corto
        if short_name:
            existing_club = Club.objects.filter(
                short_name__iexact=short_name
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing_club.exists():
                raise forms.ValidationError(
                    f'Ya existe un club con el nombre corto "{short_name}"'
                )
        
        return cleaned_data


class TeamSearchForm(forms.Form):
    """Formulario de búsqueda de equipos"""
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar equipos...'
        })
    )
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label='Todas las categorías',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    club = forms.ModelChoiceField(
        queryset=Club.objects.all(),
        required=False,
        empty_label='Todos los clubs',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )


class ClubSearchForm(forms.Form):
    """Formulario de búsqueda de clubs"""
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar clubs...'
        })
    )


class TeamFilterForm(forms.Form):
    """Formulario de filtros para equipos"""
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label='Todas las categorías',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_category_filter'
        })
    )
    
    club = forms.ModelChoiceField(
        queryset=Club.objects.all(),
        required=False,
        empty_label='Todos los clubs',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'id': 'id_club_filter'
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


class ClubFilterForm(forms.Form):
    """Formulario de filtros para clubs"""
    show_all = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2',
            'id': 'id_show_all'
        })
    )