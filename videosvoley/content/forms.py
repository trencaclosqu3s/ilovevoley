from django import forms
from django.conf import settings
from .models import Video, Comment, Image, Category


class VideoForm(forms.ModelForm):
    """Formulario para crear/editar videos"""
    class Meta:
        model = Video
        fields = ['title', 'youtube_url', 'description', 'category', 'match']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ej: Partido vs Pòrtol  - 15/10/2025'
            }),
            'youtube_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://www.youtube.com/watch?v=...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Descripción opcional del partido'
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'match': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
        }
        labels = {
            'title': 'Título',
            'youtube_url': 'URL de YouTube',
            'description': 'Descripción',
            'category': 'Categoría',
            'match': 'Partido (opcional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar categorías activas
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        # Filtrar partidos relevantes (esto se actualizará cuando migremos Match)
        # self.fields['match'].queryset = Match.objects.filter(...)


class CommentForm(forms.ModelForm):
    """Formulario para comentarios en videos"""
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Escribe tu comentario...',
                'maxlength': 500
            })
        }
        labels = {
            'content': 'Comentario'
        }


class ImageUploadForm(forms.ModelForm):
    """Formulario para subir imágenes"""
    class Meta:
        model = Image
        fields = ['image', 'title', 'description', 'image_type', 'tags', 'year']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'accept': 'image/*'
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Título descriptivo de la imagen'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Descripción opcional'
            }),
            'image_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Etiquetas separadas por comas (ej: gol, victoria, senior)'
            }),
            'year': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 2020,
                'max': 2030
            })
        }
        labels = {
            'image': 'Imagen',
            'title': 'Título',
            'description': 'Descripción',
            'image_type': 'Tipo de Imagen',
            'tags': 'Etiquetas',
            'year': 'Año'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Establecer año actual por defecto
        if not self.instance.pk:
            self.fields['year'].initial = timezone.now().year


class ImageFilterForm(forms.Form):
    """Formulario para filtrar imágenes en la galería"""
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    image_type = forms.ChoiceField(
        choices=[('', 'Todos los tipos')] + Image.IMAGE_TYPES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    year = forms.ChoiceField(
        choices=[('', 'Todos los años')],
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        })
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar en títulos, descripciones y etiquetas...'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cargar años disponibles dinámicamente
        years = Image.objects.values_list('year', flat=True).distinct().order_by('-year')
        self.fields['year'].choices = [('', 'Todos los años')] + [(year, year) for year in years]


class ImageModerationForm(forms.ModelForm):
    """Formulario para moderar imágenes"""
    class Meta:
        model = Image
        fields = ['status', 'moderation_notes']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'moderation_notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': 'Notas internas de moderación...'
            })
        }
        labels = {
            'status': 'Estado',
            'moderation_notes': 'Notas de Moderación'
        }