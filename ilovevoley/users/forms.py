from django import forms
from django.contrib.auth import get_user_model

from ilovevoley.core.models import Category, Organization
from .models import CategoryPreference

User = get_user_model()


class CustomSignupForm(forms.Form):
    """Formulario personalizado de registro que incluye información familiar"""
    parent_info = forms.CharField(
        max_length=500,
        required=True,
        label='Información Familiar',
        help_text='Indica de qué niño/a eres padre/familiar (ej: "papá de Juanito de Infantil")',
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Ejemplo: Madre/Padre/etc de Pepito Pérez del equipo Infantil',
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )

    def signup(self, request, user):
        """Método llamado por allauth para guardar datos adicionales"""
        user.parent_info = self.cleaned_data['parent_info']
        user.save()


class ParentInfoForm(forms.ModelForm):
    """Formulario simple para completar información familiar"""
    
    class Meta:
        model = User
        fields = ['parent_info']
        widgets = {
            'parent_info': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ejemplo: Madre/Padre/etc de Pepito Pérez del equipo Infantil'
            }),
        }
        labels = {
            'parent_info': 'Información Familiar'
        }
        help_texts = {
            'parent_info': 'Indica de qué niño/a eres padre/familiar para que podamos aprobar tu cuenta'
        }


class UserProfileForm(forms.ModelForm):
    """Formulario para editar perfil de usuario incluyendo preferencias de categorías.

    Las categorías de interés se guardan por organización (club), por lo que el
    formulario necesita saber cuál es el tenant activo para leer y escribir el
    conjunto correcto.
    """

    class Meta:
        model = User
        fields = ['avatar', 'username', 'first_name', 'last_name', 'parent_info']
        widgets = {
            'avatar': forms.FileInput(attrs={
                'class': 'hidden',
                'accept': 'image/*,image/heic,image/heif'
            }),
            'parent_info': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ejemplo: Madre/Padre/etc de Pepito Pérez del equipo Infantil'
            }),

            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
        }
        labels = {
            'avatar': 'Foto de Perfil',
            'username': 'Nombre de Usuario',
            'first_name': 'Nombre',
            'last_name': 'Apellidos',
            'parent_info': 'Información Familiar',
        }
        help_texts = {
            'avatar': 'Sube una imagen para tu perfil (opcional)',
            'parent_info': 'Indica de qué niño/a eres padre/familiar',
        }

    def _resolve_organizations(self, organization=None):
        orgs = []
        if self.instance and self.instance.pk:
            orgs = list(
                Organization.objects.filter(
                    memberships__user=self.instance,
                    is_active=True,
                ).distinct().order_by('name')
            )
            if not orgs and self.instance.is_superuser:
                orgs = list(Organization.objects.filter(is_active=True).order_by('name'))
        if organization and organization.is_active and organization not in orgs:
            orgs.append(organization)
        return orgs

    def __init__(self, *args, organization=None, organizations=None, **kwargs):
        # Retrocompatibilidad: si se pasa 'preferred_categories' con 'organization'
        data = kwargs.get('data')
        if data is not None and organization is not None:
            org_key = f'preferred_categories_{organization.id}'
            if 'preferred_categories' in data and org_key not in data:
                if hasattr(data, 'copy'):
                    data = data.copy()
                    if hasattr(data, 'setlist'):
                        data.setlist(org_key, data.getlist('preferred_categories'))
                    else:
                        data[org_key] = data['preferred_categories']
                else:
                    data = dict(data)
                    data[org_key] = data['preferred_categories']
                kwargs['data'] = data

        super().__init__(*args, **kwargs)
        self.organization = organization
        self.organizations = (
            organizations
            if organizations is not None
            else self._resolve_organizations(organization=organization)
        )

        for org in self.organizations:
            field_name = f'preferred_categories_{org.id}'
            self.fields[field_name] = forms.ModelMultipleChoiceField(
                queryset=Category.objects.filter(is_active=True).order_by('name'),
                required=False,
                widget=forms.CheckboxSelectMultiple(attrs={
                    'class': 'h-4 w-4 text-csj-purple focus:ring-csj-purple border-gray-300 rounded'
                }),
                label=f'Categorías de Interés en {org.name}',
                help_text=f'Selecciona las categorías que te interesan en {org.name}',
            )
            if self.instance and self.instance.pk:
                preference = self.instance.category_preferences.filter(
                    organization=org
                ).first()
                if preference:
                    self.initial[field_name] = preference.categories.all()

        if organization is not None:
            org_key = f'preferred_categories_{organization.id}'
            if org_key in self.initial:
                self.initial['preferred_categories'] = self.initial[org_key]

    @property
    def organization_category_fields(self):
        """Devuelve una lista de tuplas (organization, bound_field) para iterar en plantillas."""
        fields = []
        for org in self.organizations:
            field_name = f'preferred_categories_{org.id}'
            if field_name in self.fields:
                fields.append((org, self[field_name]))
        return fields

    def save_category_preferences(self, user=None):
        user = user or self.instance
        for org in self.organizations:
            field_name = f'preferred_categories_{org.id}'
            if field_name in self.cleaned_data:
                preference, _ = CategoryPreference.objects.get_or_create(
                    user=user, organization=org
                )
                preference.categories.set(self.cleaned_data[field_name])

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            self.save_category_preferences(user)
        return user

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar:
            # Validar tamaño (5MB máximo)
            if avatar.size > 5 * 1024 * 1024:
                raise forms.ValidationError('El archivo es demasiado grande. Tamaño máximo: 5MB')
            
            # Validar tipo de archivo
            if not avatar.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif')):
                raise forms.ValidationError('Formato no válido. Use JPG, PNG, WebP o HEIC')

        return avatar

