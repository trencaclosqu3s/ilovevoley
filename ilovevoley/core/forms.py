"""Formularios del panel de plataforma (core)."""
from django import forms
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.models import normalize_season_name

INPUT_CSS = (
    'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md '
    'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 '
    'focus:outline-none focus:ring-2 focus:ring-csj-purple'
)

INVALID_SEASON_MSG = _('Formato de temporada no válido (ej: 2027-28).')


class SeasonWizardForm(forms.Form):
    """Paso 1 del wizard: nombre de la nueva temporada."""

    name = forms.CharField(
        label=_('Temporada'),
        max_length=20,
        help_text=_('Formato YYYY-YY, ej: 2027-28'),
        widget=forms.TextInput(attrs={'class': INPUT_CSS, 'placeholder': '2027-28'}),
    )

    def clean_name(self):
        raw = self.cleaned_data['name']
        name = normalize_season_name(raw)
        if not name:
            raise forms.ValidationError(INVALID_SEASON_MSG)
        return name


__all__ = ['SeasonWizardForm']
