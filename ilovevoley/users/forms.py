from django import forms
from django.contrib.auth import get_user_model

from ilovevoley.core.models import Category
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

    preferred_categories = forms.ModelMultipleChoiceField(
        queryset=Category.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'h-4 w-4 text-csj-purple focus:ring-csj-purple border-gray-300 rounded'
        }),
        label='Categorías de Interés',
        help_text='Selecciona las categorías de contenido que te interesan en este club',
    )

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

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields['preferred_categories'].queryset = Category.objects.filter(
            is_active=True
        ).order_by('name')
        if organization is not None and self.instance.pk:
            preference = self.instance.category_preferences.filter(
                organization=organization
            ).first()
            if preference:
                self.initial['preferred_categories'] = preference.categories.all()

    def save(self, commit=True):
        user = super().save(commit=commit)
        if self.organization is not None:
            preference, _ = CategoryPreference.objects.get_or_create(
                user=user, organization=self.organization
            )
            preference.categories.set(self.cleaned_data.get('preferred_categories', []))
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

