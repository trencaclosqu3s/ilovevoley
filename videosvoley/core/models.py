from django.db import models
from django.core.validators import RegexValidator

_hex_color_validator = RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Introduce un color hexadecimal válido (ej: #9B7FBF)')


class Organization(models.Model):
    slug            = models.CharField(max_length=50, unique=True)
    name            = models.CharField(max_length=100)
    logo            = models.ImageField(upload_to='organizations/logos/', null=True, blank=True)
    primary_color   = models.CharField(max_length=7, default='#9B7FBF', validators=[_hex_color_validator])
    secondary_color = models.CharField(max_length=7, default='#7B5FA0', blank=True, validators=[_hex_color_validator])
    club_team_names = models.JSONField(default=dict, help_text='{"Senior": "SANT JOSEP", "Juvenil": "SANT JOSEP B"}')
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Organización'
        verbose_name_plural = 'Organizaciones'
        ordering = ['name']

    def __str__(self):
        return self.name
