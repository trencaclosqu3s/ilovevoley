from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class StoryComposition(models.Model):
    """Composición personalizada de la story de un partido (se guarda el layout, no el PNG)."""

    FORMAT_CHOICES = [('story', _('Story 9:16')), ('square', _('Cuadrado 1:1'))]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='story_compositions',
        verbose_name=_('Usuario'),
    )
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        related_name='story_compositions',
        verbose_name=_('Organización'),
    )
    match = models.ForeignKey(
        'competitions.Match',
        on_delete=models.CASCADE,
        related_name='story_compositions',
        verbose_name=_('Partido'),
    )
    image = models.ForeignKey(
        'content.Image',
        on_delete=models.CASCADE,
        related_name='story_compositions',
        verbose_name=_('Foto'),
    )
    card_format = models.CharField(
        max_length=10, choices=FORMAT_CHOICES, default='story', verbose_name=_('Formato')
    )
    layout = models.JSONField(default=dict, blank=True, verbose_name=_('Composición'))
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated']
        verbose_name = _('Composición de story')
        verbose_name_plural = _('Composiciones de story')

    def __str__(self):
        return f'{self.match_id} · {self.card_format} · {self.user_id}'

    def save(self, *args, **kwargs):
        # Import local: result_card importa servicios que cargan los modelos.
        from ilovevoley.competitions.result_card import CARD_SIZES, normalize_layout

        if self.card_format not in CARD_SIZES:
            raise ValueError(f'format inválido: {self.card_format}')
        # El layout se guarda siempre completo y acotado, venga de donde venga.
        self.layout = normalize_layout(self.layout, self.card_format)
        super().save(*args, **kwargs)
