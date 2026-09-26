from django import forms
from django.contrib.auth import get_user_model
from ilovevoley.videos.models import Category

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
    """Formulario para editar perfil de usuario incluyendo preferencias de categorías"""

    class Meta:
        model = User
        fields = ['avatar', 'username', 'first_name', 'last_name', 'parent_info', 'preferred_categories']
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
            'preferred_categories': forms.CheckboxSelectMultiple(attrs={
                'class': 'h-4 w-4 text-csj-purple focus:ring-csj-purple border-gray-300 rounded'
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
            'preferred_categories': 'Categorías de Interés',

        }
        help_texts = {
            'avatar': 'Sube una imagen para tu perfil (opcional)',
            'parent_info': 'Indica de qué niño/a eres padre/familiar',
            'preferred_categories': 'Selecciona las categorías de contenido que te interesan'
        }

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

