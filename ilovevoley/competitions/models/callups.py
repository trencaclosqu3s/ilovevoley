from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class FederationCallUp(models.Model):
    MODALITY_BEACH = 'beach'
    MODALITY_INDOOR = 'indoor'
    MODALITY_CHOICES = [
        (MODALITY_BEACH, _('Vóley Playa')),
        (MODALITY_INDOOR, _('Vóley Pista')),
    ]

    TYPE_SELECTION = 'selection'
    TYPE_TRAINING = 'training'
    TYPE_FOLLOW_UP = 'follow_up'
    TYPE_SUPERVISION = 'supervision'
    TYPE_CHOICES = [
        (TYPE_SELECTION, _('Selección Balear')),
        (TYPE_TRAINING, _('Tecnificación')),
        (TYPE_FOLLOW_UP, _('Seguimiento federativo')),
        (TYPE_SUPERVISION, _('Supervisión')),
    ]
    NOTIFICATION_LABELS = {
        TYPE_SELECTION: _('con la Selección Balear'),
        TYPE_TRAINING: _('de Tecnificación'),
        TYPE_FOLLOW_UP: _('de Seguimiento federativo'),
        TYPE_SUPERVISION: _('de Supervisión'),
    }

    GENDER_MALE = 'M'
    GENDER_FEMALE = 'F'
    GENDER_MIXED = 'X'
    GENDER_CHOICES = [
        (GENDER_MALE, _('Masculino')),
        (GENDER_FEMALE, _('Femenino')),
        (GENDER_MIXED, _('Mixto / No especificado')),
    ]

    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='callups',
        verbose_name=_('Temporada'),
    )
    title = models.CharField(max_length=255, verbose_name=_('Título de la circular'))
    circular_date = models.DateField(null=True, blank=True, verbose_name=_('Fecha de circular'))
    source_url = models.CharField(
        max_length=255,
        unique=True,
        verbose_name=_('Archivo PDF / URL de origen'),
        help_text=_('Nombre del fichero PDF remoto (ej: 1785324870_3735.pdf)'),
    )
    pdf_file = models.FileField(
        upload_to='callups/pdfs/%Y/',
        null=True,
        blank=True,
        verbose_name=_('Archivo PDF local'),
    )
    pdf_sha256 = models.CharField(max_length=64, blank=True, verbose_name=_('SHA256 del PDF'))

    modality = models.CharField(
        max_length=20,
        choices=MODALITY_CHOICES,
        default=MODALITY_INDOOR,
        verbose_name=_('Modalidad'),
    )
    category_name = models.CharField(max_length=50, blank=True, verbose_name=_('Categoría'))
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        default=GENDER_MIXED,
        verbose_name=_('Género'),
    )
    callup_number = models.CharField(max_length=50, blank=True, verbose_name=_('Número de convocatoria'))
    callup_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_SELECTION,
        verbose_name=_('Tipo de circular'),
        help_text=_('Selección Balear, tecnificación, seguimiento federativo o supervisión'),
    )

    raw_text = models.TextField(blank=True, verbose_name=_('Texto extraído del PDF'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'competitions_federation_callup'
        verbose_name = _('Convocatoria Federativa')
        verbose_name_plural = _('Convocatorias Federativas')
        ordering = ['-circular_date', '-created_at']

    def __str__(self):
        return self.title

    @property
    def notification_label(self):
        """Etiqueta del tipo de circular para los textos de notificación push."""
        return self.NOTIFICATION_LABELS.get(self.callup_type, _('con la Selección Balear'))


class CallUpPlayer(models.Model):
    STATUS_CONFIRMED = 'confirmed'
    STATUS_SUSPECTED = 'suspected'
    STATUS_REJECTED = 'rejected'
    STATUS_UNMATCHED = 'unmatched'
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, _('Confirmado')),
        (STATUS_SUSPECTED, _('Dudoso / Requiere Revisión')),
        (STATUS_REJECTED, _('Descartado')),
        (STATUS_UNMATCHED, _('Sin coincidencia')),
    ]

    callup = models.ForeignKey(
        FederationCallUp,
        on_delete=models.CASCADE,
        related_name='players',
        verbose_name=_('Convocatoria'),
    )
    raw_club = models.CharField(max_length=150, blank=True, verbose_name=_('Club en PDF'))
    raw_last_name = models.CharField(max_length=150, blank=True, verbose_name=_('Apellidos en PDF'))
    raw_first_name = models.CharField(max_length=150, blank=True, verbose_name=_('Nombre en PDF'))
    raw_birth_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_('Año nacimiento en PDF'))

    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='callup_players',
        verbose_name=_('Organización / Tenant'),
    )
    person = models.ForeignKey(
        'rosters.Person',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='callups',
        verbose_name=_('Persona Vinculada'),
    )
    match_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNMATCHED,
        verbose_name=_('Estado del cruce'),
    )
    match_score = models.FloatField(default=0.0, verbose_name=_('Puntuación de coincidencia'))
    match_notes = models.CharField(max_length=255, blank=True, verbose_name=_('Notas del cruce'))
    notification_sent = models.BooleanField(default=False, verbose_name=_('Notificación enviada'))

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('Revisado por'),
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Fecha de revisión'))

    class Meta:
        db_table = 'competitions_callup_player'
        verbose_name = _('Jugador Convocado')
        verbose_name_plural = _('Jugadores Convocados')
        ordering = ['callup', 'raw_last_name', 'raw_first_name']

    @property
    def raw_full_name(self):
        return f"{self.raw_first_name} {self.raw_last_name}".strip()

    def __str__(self):
        return f"{self.raw_full_name} ({self.raw_club})"
