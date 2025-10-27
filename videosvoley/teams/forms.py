from django import forms
from .models import Club, Team


class ClubForm(forms.ModelForm):
    """Formulario para crear/editar clubs"""
    class Meta:
        model = Club
        fields = [
            'federation_id', 'official_name', 'president', 'address', 'phone', 'email',
            'venue_name', 'venue_address', 'province', 'instagram', 'facebook', 
            'twitter', 'website', 'logo_url'
        ]
        widgets = {
            'federation_id': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'ID de la federación'
            }),
            'official_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre oficial del club'
            }),
            'president': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del presidente'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Dirección del club'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Teléfono de contacto'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Email de contacto'
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
                'placeholder': 'https://instagram.com/club'
            }),
            'facebook': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://facebook.com/club'
            }),
            'twitter': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://twitter.com/club'
            }),
            'website': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://club.com'
            }),
            'logo_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://ejemplo.com/logo.jpg'
            }),
        }
        labels = {
            'federation_id': 'ID de la Federación',
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
            'logo_url': 'URL del Logo',
        }


class TeamForm(forms.ModelForm):
    """Formulario para crear/editar equipos"""
    class Meta:
        model = Team
        fields = [
            'name', 'federation_id', 'club', 'sponsor_name', 'logo_url', 
            'category', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del equipo'
            }),
            'federation_id': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'ID de la federación'
            }),
            'sponsor_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Nombre del patrocinador (opcional)'
            }),
            'logo_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://ejemplo.com/logo.jpg'
            }),
        }
        labels = {
            'name': 'Nombre del Equipo',
            'federation_id': 'ID de la Federación',
            'club': 'Club',
            'sponsor_name': 'Patrocinador',
            'logo_url': 'URL del Logo',
            'category': 'Categoría',
            'is_active': 'Activo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar clubs activos
        self.fields['club'].queryset = Club.objects.all().order_by('official_name')
        # Filtrar categorías activas
        self.fields['category'].queryset = self.fields['category'].queryset.filter(is_active=True)


class TeamFilterForm(forms.Form):
    """Formulario para filtrar equipos"""
    club = forms.ModelChoiceField(
        queryset=Club.objects.all(),
        required=False,
        empty_label="Todos los clubs",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    category = forms.ChoiceField(
        choices=[('', 'Todas las categorías')],
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar equipos...'
        })
    )
    
    active_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )
    
    our_teams_only = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Obtener categorías dinámicamente
        from videosvoley.content.models import Category
        categories = Category.objects.filter(is_active=True).order_by('name')
        self.fields['category'].choices = [('', 'Todas las categorías')] + [(cat.id, cat.name) for cat in categories]


class ClubFilterForm(forms.Form):
    """Formulario para filtrar clubs"""
    province = forms.ChoiceField(
        choices=[('', 'Todas las provincias')],
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar clubs...'
        })
    )
    
    has_teams = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )
    
    has_active_teams = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-csj-purple bg-gray-100 border-gray-300 rounded focus:ring-csj-purple focus:ring-2'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Obtener provincias dinámicamente
        provinces = Club.objects.values_list('province', flat=True).distinct().exclude(province='').order_by('province')
        self.fields['province'].choices = [('', 'Todas las provincias')] + [(prov, prov) for prov in provinces]