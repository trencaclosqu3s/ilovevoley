from django.db import models
from django.utils.translation import gettext_lazy as _


class FederationCircular(models.Model):
    """Circular federativa (FVBIB) de la que solo se indexan metadatos y el enlace al PDF.

    No se descarga ni se parsea el PDF: los disciplinarios pueden incluir datos personales
    (menores) y el original sigue publicado en la web de la federación.
    """

    TIPO_COMPETITIONS = 1
    TIPO_DISCIPLINARY = 6
    TIPO_BEACH = 8
    TIPO_TRAINING = 9
    TIPO_RULES = 11
    TIPO_REFEREES = 12
    TIPO_FVBIB_DOCS = 13
    TIPO_TRANSPARENCY = 15
    TIPO_CHOICES = [
        (TIPO_COMPETITIONS, _('Competiciones')),
        (TIPO_DISCIPLINARY, _('Comité de competición')),
        (TIPO_BEACH, _('Vóley playa')),
        (TIPO_TRAINING, _('Formación')),
        (TIPO_RULES, _('Normas y reglamentos')),
        (TIPO_REFEREES, _('Árbitros')),
        (TIPO_FVBIB_DOCS, _('Documentos FVBIB')),
        (TIPO_TRANSPARENCY, _('Transparencia')),
    ]

    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='circulars',
        verbose_name=_('Temporada'),
    )
    tipo = models.PositiveSmallIntegerField(choices=TIPO_CHOICES, verbose_name=_('Tipo'))
    title = models.CharField(max_length=255, verbose_name=_('Título'))
    circular_date = models.DateField(null=True, blank=True, verbose_name=_('Fecha de circular'))
    file_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Fichero PDF remoto'),
        help_text=_('Vacío si la circular no tiene PDF adjunto.'),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Circular federativa')
        verbose_name_plural = _('Circulares federativas')
        ordering = ['-circular_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['tipo', 'title', 'circular_date'],
                name='unique_federation_circular',
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def pdf_url(self):
        if not self.file_name:
            return ''
        return f'https://voleibolib.federatio.com/upload/descargas/{self.file_name.lstrip("/")}'
