# Design: Categoría en selectores de partido

**Date:** 2026-04-29

## Problema

Al seleccionar un partido en formularios (subir vídeo, subir foto) y en el admin (Vídeo, Imagen), el desplegable muestra `"EQUIPO A vs EQUIPO B - DD/MM/YYYY"` sin indicar la categoría. Cuando hay dos partidos del mismo fin de semana entre clubes distintos con diferente categoría, es difícil distinguirlos.

## Solución

Modificar `Match.__str__` para incluir la categoría al final entre corchetes.

**Formato resultante:** `SANT JOSEP vs PÒRTOL - 15/10/2025 [Senior Fem]`

Si el partido no tiene liga o la liga no tiene categorías asignadas, el string no incluye el sufijo (comportamiento graceful).

## Cambios

### 1. `videosvoley/videos/models.py` — `Match.__str__`

```python
def __str__(self):
    base = f'{self.home_team_display} vs {self.away_team_display} - {self.match_date.strftime("%d/%m/%Y")}'
    if self.league_id:
        cats = self.league.categories.all()
        if cats:
            cat_str = ', '.join(cat.name for cat in cats)
            return f'{base} [{cat_str}]'
    return base
```

### 2. `videosvoley/videos/forms.py` — querysets en formularios

Añadir `prefetch_related('league__categories')` en los dos métodos `_setup_match_queryset` (`VideoForm` e `ImageUploadForm`) para evitar N+1 al renderizar los `<select>`.

## Alcance

- Sin migraciones
- Sin modelos nuevos
- Sin vistas nuevas
- Afecta: todos los `Select` y autocompletes que usan `Match.__str__` (front + admin)
