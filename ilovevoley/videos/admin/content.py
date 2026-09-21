"""Admin de content movido a ilovevoley.content.admin.content.

Se reexporta ImageInline para uso en inlines de otras apps (ej. MatchAdmin)
sin duplicar registros en el admin site.
"""
from ilovevoley.content.admin.content import ImageInline  # noqa: F401

__all__ = ['ImageInline']
