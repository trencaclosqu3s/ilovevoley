"""Consultas y anotaciones para las fotos favoritas.

El contador y el estado "favorita del usuario" se calculan con subconsultas en
lugar de un JOIN con ``COUNT`` para poder combinarlos con las anotaciones de
ventana que ya usan las portadas de los álbumes sin romper su ``GROUP BY``.
"""

from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from .models import Image, ImageFavorite


def favorite_count_expression():
    """Expresión anotable con el número de favoritos de cada foto."""
    return Coalesce(
        Subquery(
            ImageFavorite.objects.filter(image=OuterRef('pk'))
            .values('image')
            .annotate(total=Count('pk'))
            .values('total')
        ),
        Value(0),
        output_field=IntegerField(),
    )


def annotate_favorites(queryset, user):
    """Anota ``favorite_count`` y, si hay usuario, ``is_favorite``."""
    queryset = queryset.annotate(favorite_count=favorite_count_expression())
    if user is not None and getattr(user, 'is_authenticated', False):
        queryset = queryset.annotate(
            is_favorite=Exists(
                ImageFavorite.objects.filter(image=OuterRef('pk'), user=user)
            )
        )
    return queryset


def match_top_images(match, tenant, *, user=None, limit=3):
    """Fotos aprobadas del partido en el tenant con más favoritos.

    Solo devuelve fotos con al menos un favorito y llega hasta ``limit``.
    """
    queryset = Image.objects.filter(
        match=match, organization=tenant, status='approved'
    )
    queryset = annotate_favorites(queryset, user)
    return list(
        queryset.filter(favorite_count__gt=0).order_by(
            '-favorite_count', '-upload_date'
        )[:limit]
    )
