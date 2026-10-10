from django import forms
from django.conf import settings
from django.db.models import Q
from django.forms import formset_factory
from django.utils.translation import gettext_lazy as _

from ilovevoley.competitions.models import Match
from ilovevoley.core.mixins import get_club_team_filter
from ilovevoley.core.models import Category, Season
from .models import Comment, Image, Video


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = ['title', 'youtube_url', 'description', 'category', 'match', 'set_number', 'season']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': _('Ej: Partido vs Pòrtol  - 15/10/2025')
            }),
            'youtube_url': forms.URLInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': 'https://www.youtube.com/watch?v=...'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': _('Descripción opcional del partido')
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'match': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
            'set_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 1,
                'placeholder': _('Ej: 1 (opcional)'),
            }),
            'season': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
            }),
        }
        labels = {
            'title': _('Título'),
            'youtube_url': _('URL de YouTube'),
            'description': _('Descripción'),
            'category': _('Categoría'),
            'match': _('Partido (opcional)'),
            'set_number': _('Set (opcional)'),
            'season': _('Temporada (opcional)'),
        }

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)
        # Hacer el campo match opcional
        self.fields['match'].required = False
        self.fields['season'].required = False
        self.fields['set_number'].required = False
        if not self.instance.pk:
            self.fields['season'].initial = Season.objects.current()

        # Filtrar partidos inteligentemente basado en categoría y equipos del club
        self._setup_match_queryset()

    def _setup_match_queryset(self):
        """Configura el queryset de partidos basado en categoría y equipos del club"""
        from django.utils import timezone
        
        # Si hay una categoría preseleccionada, filtrar por equipos de esa categoría
        category = None
        if self.data and 'category' in self.data:
            try:
                category = Category.objects.get(id=self.data['category'])
            except (Category.DoesNotExist, ValueError):
                pass
        elif self.instance and self.instance.category:
            category = self.instance.category

        # Construir query base para equipos del club
        club_query = get_club_team_filter(self.organization)

        # Si hay categoría específica, filtrar por equipos de esa categoría
        if category:
            # Filtrar por equipos que tengan la categoría específica O por liga de esa categoría
            category_query = (Q(home_team__category=category) | Q(away_team__category=category) |
                            Q(league__categories=category))
            
            # Combinar: partidos del club Y de la categoría específica
            final_query = club_query & category_query
            
        else:
            # Sin categoría específica, mostrar todos los partidos del club
            final_query = club_query
        
        # Fecha actual
        now = timezone.now()
        
        # Filtrar: partidos del pasado + el próximo partido futuro
        # (withdrawn excluidos automáticamente por el manager)
        # 1. Obtener todos los partidos del pasado
        past_matches = Match.objects.select_related(
            'home_team', 'away_team', 'home_team__category', 'away_team__category',
            'league'
        ).prefetch_related('league__categories').filter(final_query, match_date__lt=now)

        # 2. Obtener el próximo partido futuro (solo uno)
        next_match = Match.objects.select_related(
            'home_team', 'away_team', 'home_team__category', 'away_team__category',
            'league'
        ).prefetch_related('league__categories').filter(final_query, match_date__gte=now).order_by('match_date').first()
        
        # 3. Combinar: partidos pasados + próximo partido (si existe)
        if next_match:
            # Usar union de querysets
            self.fields['match'].queryset = (past_matches | Match.objects.filter(id=next_match.id)).order_by('-match_date')
        else:
            # Solo partidos pasados
            self.fields['match'].queryset = past_matches.order_by('-match_date')
        
        # Actualizar label basado en contexto
        if category:
            self.fields['match'].empty_label = _('Seleccionar partido de %(name)s (opcional)') % {'name': category.name}
        else:
            self.fields['match'].empty_label = _("Seleccionar partido del club (opcional)")


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent resize-none',
                'rows': 2,
                'placeholder': _('¡Añade un comentario de apoyo! 💪')
            }),
        }
        labels = {
            'content': '',
        }


class ImageUploadForm(forms.ModelForm):
    """Formulario para subida de imágenes con soporte drag & drop"""
    
    class Meta:
        model = Image
        fields = ['image', 'title', 'description', 'image_type', 'categories', 'tags', 'match', 'set_number', 'season']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'hidden',
                'id': 'image-input',
                'accept': 'image/jpeg,image/jpg,image/png,image/webp,image/heic,image/heif',
                'multiple': False
            }),
            'title': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'placeholder': _('Título descriptivo (opcional si se selecciona un partido)')
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'rows': 3,
                'placeholder': _('Descripción opcional')
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
                'placeholder': _('Ej: gol, victoria, senior, entrenamiento (separadas por comas)'),
                'data-toggle': 'tags'
            }),
            'match': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'id': 'id_match'
            }),
            'set_number': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'min': 1,
                'id': 'id_set_number',
                'placeholder': _('Ej: 1 (opcional)'),
            }),
            'season': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
                'id': 'id_season'
            }),
        }
        labels = {
            'image': _('Imagen'),
            'title': _('Título'),
            'description': _('Descripción'),
            'image_type': _('Tipo de imagen'),
            'categories': _('Categorías'),
            'tags': _('Etiquetas'),
            'match': _('Partido (opcional)'),
            'set_number': _('Set (opcional)'),
            'season': _('Temporada (opcional)'),
        }

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)

        # Hacer campos opcionales
        self.fields['title'].required = False
        self.fields['description'].required = False
        self.fields['categories'].required = False
        self.fields['tags'].required = False
        self.fields['match'].required = False
        self.fields['season'].required = False
        self.fields['set_number'].required = False
        if not self.instance.pk:
            self.fields['season'].initial = Season.objects.current()

        # Configurar queryset de categorías activas
        self.fields['categories'].queryset = Category.objects.filter(is_active=True).order_by('name')
        self.fields['categories'].help_text = _('Selecciona una o más categorías (opcional si se vincula un partido)')

        # Filtrar partidos del club
        self._setup_match_queryset()

        # Configurar lógica condicional para el campo match
        self._setup_conditional_logic()

    def _setup_match_queryset(self):
        """Configura el queryset de partidos basado en equipos del club"""
        from django.utils import timezone

        # Filtrar partidos del club ordenados por fecha
        club_query = get_club_team_filter(self.organization)
        
        # Fecha actual
        now = timezone.now()
        
        # Filtrar: partidos del pasado + el próximo partido futuro
        # (withdrawn excluidos automáticamente por el manager)
        # 1. Obtener todos los partidos del pasado
        past_matches = Match.objects.select_related(
            'home_team', 'away_team', 'league'
        ).prefetch_related('league__categories').filter(club_query, match_date__lt=now)

        # 2. Obtener el próximo partido futuro (solo uno)
        next_match = Match.objects.select_related(
            'home_team', 'away_team', 'league'
        ).prefetch_related('league__categories').filter(club_query, match_date__gte=now).order_by('match_date').first()
        
        # 3. Combinar: partidos pasados + próximo partido (si existe)
        if next_match:
            # Usar union de querysets
            self.fields['match'].queryset = (past_matches | Match.objects.filter(id=next_match.id)).order_by('-match_date')
        else:
            # Solo partidos pasados
            self.fields['match'].queryset = past_matches.order_by('-match_date')
        
        self.fields['match'].empty_label = _("Seleccionar partido (opcional)")
    
    def _setup_conditional_logic(self):
        """Configura la lógica condicional entre tipo de imagen y partido"""
        # Si hay datos del formulario, verificar lógica
        if self.data and 'image_type' in self.data:
            image_type = self.data.get('image_type')
            if image_type == 'match':
                # Para imágenes de partido, sugerir que seleccionen un partido
                self.fields['match'].help_text = _('Se recomienda seleccionar el partido correspondiente')
            else:
                # Para otros tipos, el partido es completamente opcional
                self.fields['match'].help_text = _('Opcional: vincula la imagen a un partido específico')

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Validar tamaño (10MB máximo)
            if image.size > 10 * 1024 * 1024:
                raise forms.ValidationError(_('El archivo es demasiado grande. Tamaño máximo: 10MB'))
            
            # Validar tipo de archivo
            if not image.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif')):
                raise forms.ValidationError(_('Formato no válido. Use JPG, PNG, WebP o HEIC'))
        
        return image
    
    def clean_tags(self):
        """Validar y limpiar etiquetas"""
        tags = self.cleaned_data.get('tags', '')
        if tags:
            # Limpiar etiquetas: separar por comas, limpiar espacios, eliminar vacías
            cleaned_tags = [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
            # Limitar número de etiquetas
            if len(cleaned_tags) > 10:
                raise forms.ValidationError(_('Máximo 10 etiquetas permitidas'))
            # Limitar longitud de cada etiqueta
            for tag in cleaned_tags:
                if len(tag) > 30:
                    raise forms.ValidationError(
                        _('La etiqueta "%(tag)s" es demasiado larga (máximo 30 caracteres)') % {'tag': tag}
                    )
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
        ('approve', _('Aprobar')),
        ('reject', _('Rechazar')),
    ]
    
    action = forms.ChoiceField(
        choices=MODERATION_ACTIONS,
        widget=forms.RadioSelect,
        label=_('Acción')
    )
    
    class Meta:
        model = Image
        fields = ['moderation_notes']
        widgets = {
            'moderation_notes': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg',
                'rows': 3,
                'placeholder': _('Notas de moderación (opcional)')
            }),
        }
        labels = {
            'moderation_notes': _('Notas'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['moderation_notes'].required = False


class ImageFilterForm(forms.Form):
    """Formulario para filtrar la galería de imágenes"""
    
    STATUS_CHOICES = [
        ('', _('Todos los estados')),
        ('pending', _('Pendientes')),
        ('approved', _('Aprobadas')),
        ('rejected', _('Rechazadas')),
    ]
    
    IMAGE_TYPE_CHOICES = [
        ('', _('Todos los tipos')),
        ('match', _('Partido')),
        ('celebration', _('Celebración')),
        ('training', _('Entrenamiento')),
        ('team_photo', _('Foto de Equipo')),
        ('facilities', _('Instalaciones')),
        ('other', _('Otro')),
    ]
    
    MATCH_FILTER_CHOICES = [
        ('', _('Todas las imágenes')),
        ('with_match', _('Con partido vinculado')),
        ('without_match', _('Sin partido vinculado')),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': _('Buscar por título, descripción, etiquetas o deportista...')
        }),
        label=_('Buscar')
    )
    
    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent',
            'placeholder': _('Buscar por etiquetas específicas...')
        }),
        label=_('Etiquetas')
    )
    
    image_type = forms.ChoiceField(
        choices=IMAGE_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label=_('Tipo')
    )
    
    match_filter = forms.ChoiceField(
        choices=MATCH_FILTER_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label=_('Partido')
    )
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        empty_label=_('Todas las categorías'),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label=_('Categoría')
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'
        }),
        label=_('Estado')
    )


INPUT_CSS = 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent'


class VideoEntryForm(forms.Form):
    """Fila de título + URL para el formulario de subida múltiple de vídeos."""
    title = forms.CharField(
        max_length=200,
        label=_('Título'),
        widget=forms.TextInput(attrs={
            'class': INPUT_CSS,
            'placeholder': _('Ej: Primer tiempo'),
        }),
    )
    youtube_url = forms.URLField(
        label=_('URL de YouTube'),
        widget=forms.URLInput(attrs={
            'class': INPUT_CSS,
            'placeholder': 'https://www.youtube.com/watch?v=...',
        }),
    )
    set_number = forms.IntegerField(
        required=False,
        min_value=1,
        label=_('Set (opcional)'),
        widget=forms.NumberInput(attrs={
            'class': INPUT_CSS,
            'min': 1,
            'placeholder': _('Set'),
        }),
    )


VideoEntryFormSet = formset_factory(VideoEntryForm, extra=2, can_delete=True)


class VideoBulkSharedForm(forms.Form):
    """Campos compartidos (partido y categoría) para la subida múltiple de vídeos."""
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True).order_by('name'),
        required=False,
        label=_('Categoría'),
        empty_label=_('Todas las categorías'),
        widget=forms.Select(attrs={'class': INPUT_CSS, 'id': 'id_category'}),
    )
    match = forms.ModelChoiceField(
        queryset=Match.objects.none(),
        required=False,
        label=_('Partido (opcional)'),
        empty_label=_('Seleccionar partido del club (opcional)'),
        widget=forms.Select(attrs={'class': INPUT_CSS, 'id': 'id_match'}),
    )

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)
        self._setup_match_queryset()

    def _setup_match_queryset(self):
        from django.utils import timezone

        category = None
        if self.data and 'category' in self.data:
            try:
                category = Category.objects.get(id=self.data['category'])
            except (Category.DoesNotExist, ValueError):
                pass

        club_query = get_club_team_filter(self.organization)

        if category:
            category_query = (
                Q(home_team__category=category) | Q(away_team__category=category) |
                Q(league__categories=category)
            )
            final_query = club_query & category_query
            self.fields['match'].empty_label = _('Seleccionar partido de %(name)s (opcional)') % {'name': category.name}
        else:
            final_query = club_query

        now = timezone.now()
        base_qs = Match.objects.select_related(
            'home_team', 'away_team', 'home_team__category', 'away_team__category', 'league'
        ).prefetch_related('league__categories')

        past = base_qs.filter(final_query, match_date__lt=now)
        next_match = base_qs.filter(final_query, match_date__gte=now).order_by('match_date').first()

        if next_match:
            self.fields['match'].queryset = (past | Match.objects.filter(id=next_match.id)).order_by('-match_date')
        else:
            self.fields['match'].queryset = past.order_by('-match_date')


__all__ = [
    'VideoForm',
    'CommentForm',
    'ImageUploadForm',
    'ImageModerationForm',
    'ImageFilterForm',
    'INPUT_CSS',
    'VideoEntryForm',
    'VideoEntryFormSet',
    'VideoBulkSharedForm',
]
