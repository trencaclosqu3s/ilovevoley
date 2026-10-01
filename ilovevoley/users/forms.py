from django import forms
from django.contrib.auth import get_user_model

from ilovevoley.core.models import Category, Organization
from .models import CategoryPreference, NotificationPreference, NotificationType

AVAILABLE_NOTIFICATION_TYPES = list(NotificationType.choices)


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

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if self.instance and self.instance.pk:
            self.organizations = self.instance.profile_organizations(tenant=organization)
        elif organization and getattr(organization, 'is_active', False):
            self.organizations = [organization]
        else:
            self.organizations = []

        preferences_by_org = {}
        disabled_notifications_by_org = {}
        if self.instance and self.instance.pk and self.organizations:
            preferences_by_org = {
                pref.organization_id: pref.categories.all()
                for pref in (
                    self.instance.category_preferences.filter(
                        organization__in=self.organizations
                    ).prefetch_related('categories')
                )
            }
            from collections import defaultdict
            disabled_map = defaultdict(set)
            for notif_pref in self.instance.notification_preferences.filter(
                organization__in=self.organizations,
                is_enabled=False,
            ):
                disabled_map[notif_pref.organization_id].add(notif_pref.notification_type)
            disabled_notifications_by_org = disabled_map

        all_type_values = [t for t, _ in AVAILABLE_NOTIFICATION_TYPES]

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
            if org.id in preferences_by_org:
                self.initial[field_name] = preferences_by_org[org.id]

            notif_field_name = f'notification_types_{org.id}'
            self.fields[notif_field_name] = forms.MultipleChoiceField(
                choices=AVAILABLE_NOTIFICATION_TYPES,
                required=False,
                widget=forms.CheckboxSelectMultiple(attrs={
                    'class': 'h-4 w-4 text-csj-purple focus:ring-csj-purple border-gray-300 rounded'
                }),
                label=f'Avisos Push en {org.name}',
                help_text=f'Selecciona qué avisos push deseas recibir en {org.name}',
            )
            disabled = disabled_notifications_by_org.get(org.id, set())
            self.initial[notif_field_name] = [t for t in all_type_values if t not in disabled]

    @property
    def organization_category_fields(self):
        """Devuelve una lista de tuplas (organization, bound_field) para iterar en plantillas."""
        fields = []
        for org in self.organizations:
            field_name = f'preferred_categories_{org.id}'
            if field_name in self.fields:
                fields.append((org, self[field_name]))
        return fields

    @property
    def organization_notification_fields(self):
        """Devuelve una lista de tuplas (organization, bound_field) para iterar en plantillas."""
        fields = []
        for org in self.organizations:
            field_name = f'notification_types_{org.id}'
            if field_name in self.fields:
                fields.append((org, self[field_name]))
        return fields

    def save_category_preferences(self, user=None):
        from django.db import transaction
        user = user or self.instance
        with transaction.atomic():
            for org in self.organizations:
                field_name = f'preferred_categories_{org.id}'
                if field_name in self.cleaned_data:
                    selected = self.cleaned_data[field_name]
                    pref = user.category_preferences.filter(organization=org).first()
                    if selected:
                        if not pref:
                            pref = CategoryPreference.objects.create(
                                user=user, organization=org
                            )
                        pref.categories.set(selected)
                    elif pref:
                        pref.categories.clear()

    def save_notification_preferences(self, user=None):
        from django.db import transaction
        user = user or self.instance
        with transaction.atomic():
            for org in self.organizations:
                field_name = f'notification_types_{org.id}'
                if field_name in self.cleaned_data:
                    selected = set(self.cleaned_data[field_name])
                    for type_val, _ in AVAILABLE_NOTIFICATION_TYPES:
                        is_enabled = type_val in selected
                        NotificationPreference.objects.update_or_create(
                            user=user,
                            organization=org,
                            notification_type=type_val,
                            defaults={'is_enabled': is_enabled},
                        )

    def _save_m2m(self):
        super()._save_m2m()
        self.save_category_preferences(self.instance)
        self.save_notification_preferences(self.instance)


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

