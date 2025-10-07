from django import forms
from django.conf import settings
from django.db.models import Q
from .models import Video, Comment, Category, Match, Team, Image


class VideoForm(forms.ModelForm):
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
        # Hacer el campo match opcional
        self.fields['match'].required = False
        
        # Filtrar partidos inteligentemente basado en categoría y equipos del club
        self._setup_match_queryset()
        
    def _setup_match_queryset(self):
        """Configura el queryset de partidos basado en categoría y equipos del club"""
        # Obtener configuración de equipos del club
        club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        
        # Si hay una categoría preseleccionada, filtrar por equipos de esa categoría
        category = None
        if self.data and 'category' in self.data:
            try:
                from .models import Category
                category = Category.objects.get(id=self.data['category'])
            except (Category.DoesNotExist, ValueError):
                pass
        elif self.instance and self.instance.category:
            category = self.instance.category
        
        # Construir query base para equipos del club
        club_query = (Q(home_team__name__icontains=club_team_name) | 
                     Q(away_team__name__icontains=club_team_name))
        
        # Si hay categoría específica, filtrar por equipos de esa categoría
        if category:
            # Filtrar por equipos que tengan la categoría específica O por liga de esa categoría
            category_query = (Q(home_team__category=category) | Q(away_team__category=category) |
                            Q(league__category=category))
            
            # Combinar: partidos del club Y de la categoría específica
            final_query = club_query & category_query
            
        else:
            # Sin categoría específica, mostrar todos los partidos del club
            final_query = club_query
        
        self.fields['match'].queryset = Match.objects.select_related(
            'home_team', 'away_team', 'home_team__category', 'away_team__category', 
            'league', 'league__category'
        ).filter(final_query).order_by('-match_date')
        
        # Actualizar label basado en contexto
        if category:
            self.fields['match'].empty_label = f"Seleccionar partido de {category.name} (opcional)"
        else:
            self.fields['match'].empty_label = "Seleccionar partido del club (opcional)"


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent resize-none',
                'rows': 2,
                'placeholder': '¡Añade un comentario de apoyo! 💪'
            }),
        }
        labels = {
            'content': '',
        }


class MatchAdminForm(forms.ModelForm):
    """Formulario personalizado para el admin de Match con filtrado por categoría"""
    
    filter_by_category = forms.BooleanField(
        required=False, 
        initial=True,
        label='Filtrar equipos por categoría de la liga',
        help_text='Desmarca para ver todos los equipos disponibles'
    )
    
    class Meta:
        model = Match
        fields = '__all__'
        widgets = {
            'match_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Configurar filtrado por defecto
        filter_by_category = True
        league_category = None
        
        # Si estamos editando un match existente y tiene liga
        if self.instance and self.instance.pk and self.instance.league:
            league_category = self.instance.league.category
            
            # Verificar si se envió el formulario con el checkbox
            if self.data and 'filter_by_category' in self.data:
                filter_by_category = self.data.get('filter_by_category') == 'on'
        
        # Si hay datos POST sobre league, obtener la categoría de esa liga
        elif self.data and 'league' in self.data and self.data['league']:
            try:
                from .models import League
                league = League.objects.get(id=self.data['league'])
                league_category = league.category
                if self.data and 'filter_by_category' in self.data:
                    filter_by_category = self.data.get('filter_by_category') == 'on'
            except (League.DoesNotExist, ValueError):
                pass
        
        # Aplicar filtrado de equipos
        if filter_by_category and league_category:
            # Filtrar equipos por la categoría de la liga
            filtered_teams = Team.objects.filter(category=league_category).order_by('name')
            self.fields['home_team'].queryset = filtered_teams
            self.fields['away_team'].queryset = filtered_teams
            
            # Actualizar help text
            self.fields['home_team'].help_text = f'Equipos de la categoría: {league_category.name}'
            self.fields['away_team'].help_text = f'Equipos de la categoría: {league_category.name}'
        else:
            # Mostrar todos los equipos
            self.fields['home_team'].queryset = Team.objects.all().order_by('name')
            self.fields['away_team'].queryset = Team.objects.all().order_by('name')
        
        # Agregar clases CSS y atributos para JavaScript
        self.fields['filter_by_category'].widget.attrs.update({
            'id': 'id_filter_by_category'
        })
        
        # Establecer valor inicial del checkbox
        if 'filter_by_category' not in self.data:
            self.fields['filter_by_category'].initial = True


class ImageUploadForm(forms.ModelForm):
    """Formulario para subida de imágenes con soporte drag & drop"""
    
    class Meta:
        model = Image
        fields = ['image', 'title', 'description', 'image_type', 'categories', 'tags', 'match']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'hidden',
                'id': 'image-input',
                'accept': 'image/jpeg,image/jpg,image/png,image/webp',
                'multiple': False
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
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'id': 'id_image_type'
            }),
            'categories': forms.CheckboxSelectMultiple(attrs={
                'class': 'space-y-2'
            }),
            'tags': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'Ej: gol, victoria, senior, entrenamiento (separadas por comas)',
                'data-toggle': 'tags'
            }),
            'match': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'id': 'id_match'
            }),
        }
        labels = {
            'image': 'Imagen',
            'title': 'Título',
            'description': 'Descripción',
            'image_type': 'Tipo de imagen',
            'categories': 'Categorías',
            'tags': 'Etiquetas',
            'match': 'Partido (opcional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hacer campos opcionales
        self.fields['description'].required = False
        self.fields['categories'].required = False
        self.fields['tags'].required = False
        self.fields['match'].required = False
        
        # Configurar queryset de categorías activas
        self.fields['categories'].queryset = Category.objects.filter(is_active=True).order_by('name')
        self.fields['categories'].help_text = 'Selecciona una o más categorías (opcional si se vincula un partido)'
        
        # Filtrar partidos del club
        self._setup_match_queryset()
        
        # Configurar lógica condicional para el campo match
        self._setup_conditional_logic()
        
    def _setup_match_queryset(self):
        """Configura el queryset de partidos basado en equipos del club"""
        club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        
        # Filtrar partidos del club ordenados por fecha
        club_query = (Q(home_team__name__icontains=club_team_name) | 
                     Q(away_team__name__icontains=club_team_name))
        
        self.fields['match'].queryset = Match.objects.select_related(
            'home_team', 'away_team', 'league'
        ).filter(club_query).order_by('-match_date')
        
        self.fields['match'].empty_label = "Seleccionar partido (opcional)"
    
    def _setup_conditional_logic(self):
        """Configura la lógica condicional entre tipo de imagen y partido"""
        # Si hay datos del formulario, verificar lógica
        if self.data and 'image_type' in self.data:
            image_type = self.data.get('image_type')
            if image_type == 'match':
                # Para imágenes de partido, sugerir que seleccionen un partido
                self.fields['match'].help_text = 'Se recomienda seleccionar el partido correspondiente'
            else:
                # Para otros tipos, el partido es completamente opcional
                self.fields['match'].help_text = 'Opcional: vincula la imagen a un partido específico'

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Validar tamaño (10MB máximo)
            if image.size > 10 * 1024 * 1024:
                raise forms.ValidationError('El archivo es demasiado grande. Tamaño máximo: 10MB')
            
            # Validar tipo de archivo
            if not image.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                raise forms.ValidationError('Formato no válido. Use JPG, PNG o WebP')
        
        return image
    
    def clean_tags(self):
        """Validar y limpiar etiquetas"""
        tags = self.cleaned_data.get('tags', '')
        if tags:
            # Limpiar etiquetas: separar por comas, limpiar espacios, eliminar vacías
            cleaned_tags = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
            # Limitar número de etiquetas
            if len(cleaned_tags) > 10:
                raise forms.ValidationError('Máximo 10 etiquetas permitidas')
            # Limitar longitud de cada etiqueta
            for tag in cleaned_tags:
                if len(tag) > 30:
                    raise forms.ValidationError(f'La etiqueta "{tag}" es demasiado larga (máximo 30 caracteres)')
            return ', '.join(cleaned_tags)
        return ''
    
    def clean(self):
        """Validación global del formulario"""
        cleaned_data = super().clean()
        image_type = cleaned_data.get('image_type')
        match = cleaned_data.get('match')
        
        # Si es tipo 'match' pero no hay partido seleccionado, solo mostrar advertencia como ayuda
        # No bloquear el formulario - será una recomendación visual en el frontend
        
        return cleaned_data


class ImageModerationForm(forms.ModelForm):
    """Formulario para moderación de imágenes por admin"""
    
    MODERATION_ACTIONS = [
        ('approve', 'Aprobar'),
        ('reject', 'Rechazar'),
    ]
    
    action = forms.ChoiceField(
        choices=MODERATION_ACTIONS,
        widget=forms.RadioSelect,
        label='Acción'
    )
    
    class Meta:
        model = Image
        fields = ['moderation_notes']
        widgets = {
            'moderation_notes': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg',
                'rows': 3,
                'placeholder': 'Notas de moderación (opcional)'
            }),
        }
        labels = {
            'moderation_notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['moderation_notes'].required = False


class ImageFilterForm(forms.Form):
    """Formulario para filtrar la galería de imágenes"""
    
    STATUS_CHOICES = [
        ('', 'Todos los estados'),
        ('pending', 'Pendientes'),
        ('approved', 'Aprobadas'),
        ('rejected', 'Rechazadas'),
    ]
    
    IMAGE_TYPE_CHOICES = [
        ('', 'Todos los tipos'),
        ('match', 'Partido'),
        ('celebration', 'Celebración'),
        ('training', 'Entrenamiento'),
        ('team_photo', 'Foto de Equipo'),
        ('facilities', 'Instalaciones'),
        ('other', 'Otro'),
    ]
    
    MATCH_FILTER_CHOICES = [
        ('', 'Todas las imágenes'),
        ('with_match', 'Con partido vinculado'),
        ('without_match', 'Sin partido vinculado'),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar por título, descripción o etiquetas...'
        }),
        label='Buscar'
    )
    
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Buscar por etiquetas específicas...'
        }),
        label='Etiquetas'
    )
    
    image_type = forms.ChoiceField(
        choices=IMAGE_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label='Tipo'
    )
    
    match_filter = forms.ChoiceField(
        choices=MATCH_FILTER_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label='Partido'
    )
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label='Todas las categorías',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label='Categoría'
    )
    
    year = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': 'Año'
        }),
        label='Año'
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label='Estado'
    )