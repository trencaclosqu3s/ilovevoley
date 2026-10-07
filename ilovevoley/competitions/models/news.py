from django.db import models
from django.utils.translation import gettext_lazy as _


class FederationNews(models.Model):
    """Noticia publicada por la FVBIB: solo metadatos y enlace a la web oficial (#370).

    No se guarda el cuerpo HTML: evita sanitizarlo y el contenido mezclado catalán/castellano.
    """

    federation_id = models.PositiveIntegerField(unique=True)
    published_at = models.DateField(null=True, blank=True, verbose_name=_('Fecha'))
    title = models.CharField(max_length=500, verbose_name=_('Titular'))
    kind = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_('Tipo'),
        help_text=_('Etiqueta de la federación (Generales, Arbitros…); la playa reciente llega como Generales.'),
    )
    club_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('Club'),
        help_text=_('Solo en actividades de clubes (campus, eventos), tal como lo publica la federación.'),
    )
    image_name = models.CharField(max_length=255, blank=True, verbose_name=_('Imagen remota'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Noticia federativa')
        verbose_name_plural = _('Noticias federativas')
        ordering = ['-published_at', '-federation_id']

    def __str__(self):
        return self.title

    @property
    def url(self):
        return f'https://voleibolib.net/noticia?id={self.federation_id}'

    @property
    def image_url(self):
        return f'https://voleibolib.federatio.com/upload/{self.image_name}' if self.image_name else ''
