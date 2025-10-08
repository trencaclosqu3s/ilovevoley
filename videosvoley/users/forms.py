from django import forms
from django.contrib.auth import get_user_model
from videosvoley.videos.models import Category

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
        fields = ['avatar', 'username', 'email', 'first_name', 'last_name', 'parent_info', 'preferred_categories', 'calendar_sync_enabled', 'google_calendar_id']
        widgets = {
            'avatar': forms.FileInput(attrs={
                'class': 'hidden',
                'accept': 'image/*'
            }),
            'parent_info': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ejemplo: Madre/Padre/etc de Pepito Pérez del equipo Infantil'
            }),
            'preferred_categories': forms.CheckboxSelectMultiple(attrs={
                'class': 'h-4 w-4 text-csj-purple focus:ring-csj-purple border-gray-300 rounded'
            }),
            'calendar_sync_enabled': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-csj-purple focus:ring-csj-purple border-gray-300 rounded'
            }),
            'google_calendar_id': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Deja vacío para usar calendar principal'
            }),
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'email': forms.EmailInput(attrs={
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
            'email': 'Correo Electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellidos',
            'parent_info': 'Información Familiar',
            'preferred_categories': 'Categorías de Interés',
            'calendar_sync_enabled': 'Sincronizar con Google Calendar',
            'google_calendar_id': 'ID del Calendar de Google (opcional)'
        }
        help_texts = {
            'avatar': 'Sube una imagen para tu perfil (opcional)',
            'parent_info': 'Indica de qué niño/a eres padre/familiar',
            'preferred_categories': 'Selecciona las categorías de contenido que te interesan',
            'calendar_sync_enabled': 'Sincronizar automáticamente los partidos de tus categorías preferidas con Google Calendar',
            'google_calendar_id': 'ID del calendar específico donde sincronizar eventos. Deja vacío para usar el calendar principal'
        }

    def __init__(self, *args, **kwargs):
        super(UserProfileForm, self).__init__(*args, **kwargs)
        # Hacer que el email no sea editable una vez creado
        if self.instance and self.instance.pk:
            self.fields['email'].widget.attrs['readonly'] = True
            
        # Mostrar campos de calendar solo si el usuario tiene conexión con Google
        if self.instance and self.instance.pk:
            if not self.instance.has_google_calendar_permissions():
                # Deshabilitar campos de calendar si no tiene permisos
                self.fields['calendar_sync_enabled'].widget.attrs['disabled'] = True
                self.fields['google_calendar_id'].widget.attrs['disabled'] = True
                self.fields['calendar_sync_enabled'].help_text = 'Necesitas iniciar sesión con Google para habilitar esta función'
                self.fields['google_calendar_id'].help_text = 'Necesitas permisos de Google Calendar para usar esta función'

