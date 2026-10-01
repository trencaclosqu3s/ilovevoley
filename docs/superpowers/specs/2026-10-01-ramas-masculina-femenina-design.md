# Soporte de Ramas Masculina/Femenina a Nivel de Club y Equipos

**Fecha:** 2026-10-01  
**Estado:** Propuesta aprobada para especificación  
**Issue:** [#293](https://github.com/trencaclosqu3s/ilovevoley/issues/293)  
**Apps afectadas:** `ilovevoley.core`, `ilovevoley.teams`, `ilovevoley.competitions`, `ilovevoley.users`

---

## 1. Contexto y Diagnóstico del Problema

### El problema
Hoy no existe ninguna noción estructurada de género o rama (masculino, femenino, mixto) en el modelo de datos. El género vive únicamente como **texto libre dentro de nombres**:

- `Category.name`: `"Senior Femenino"`, `"Infantil Masculino"`, o simplemente `"Senior"` (ambiguo).
- `League.name`: `"ALEVIN MASCULINO 4X4 - Fase Regular"`.

Esto impide clasificar de forma fiable los equipos de la cantera y, sobre todo, filtrar automáticamente los avisos federativos según la rama que compite cada club. Un club como Sant Josep o Sóller puede tener sección femenina, pero como en la app solo se gestionan equipos masculinos, hoy no hay forma de configuran qué ramas interesan.

### Estado actual relevante
- `Organization` (tenant) tiene `club_team_names` (JSON keyed por etiqueta de categoría) y `club` (FK al `Club` federativo), pero nada de ramas.
- El matching de partidos/equipos es por nombre (`get_club_team_filter`, `get_club_team_name_filter` en `core/mixins.py`) y por categoría (`match_category_ids` en `competitions/services/notifications.py`).
- Los avisos federativos (push de resultado, cambio y recordatorio; email de cambios) se seleccionan por club y se filtran por categoría vía `CategoryPreference`.
- No hay DRF ni serializers: toda la I/O es formularios Django + templates + admin (Unfold).

---

## 2. Decisiones de Arquitectura

1. **Género estructurado en `Category`**: nuevo campo `Category.gender` (`male` / `female` / `mixed` / vacío). Las categorías son globales; el género de una categoría genérica como `"Senior"` queda vacío (desconocido) y deberá rellenarse a mano o venir del scraping en el futuro.

2. **Género a nivel de `Team`**: nuevo campo `Team.gender` (mismo enum, vacío por defecto) con **inferencia desde la categoría**: `Team.effective_gender` = `team.gender or team.category.gender`. Esto permite distinguir un `"Senior Masculino"` de un `"Senior Femenino"` aunque compartan categoría genérica `"Senior"` (se marca el override en el equipo).

3. **Ramas activas en `Organization`**: tres booleanos `has_male_branch` (default `True`), `has_female_branch` (default `False`) y `has_mixed_branch` (default `False`). Reflejan el estado actual (solo masculino) y son la palanca para "activar" la rama femenina el día que interese, sin tocar código. Property `Organization.active_branches` → `set[str]`.

4. **Alcance del filtrado: solo avisos y suscripciones**. El matching de convocatorias (acta → dorsal → `Person`) es intra-partido y no depende del género. El scraping **no** descarta ligas por rama, y los listados de UI **no** ocultan equipos. La rama se aplica al seleccionar las organizaciones que reciben un aviso.

5. **Regla permisiva ante género desconocido**: si un partido no tiene género determinable (`match_branches` vacío), el aviso **se envía**. No se silencian datos sin clasificar.

6. **Backfill de datos vía migración `RunPython`** (regla de proyecto): se rellena `Category.gender` parseando el nombre. `Team.gender` no se materializa; se infiere en lectura.

7. **Configuración solo desde Django Admin** (Unfold). No se añade página de settings del tenant en este alcance.

---

## 3. Especificación Detallada

### 3.1. Constantes y helper de inferencia (`ilovevoley/core/models.py`)

```python
GENDER_MALE = 'male'
GENDER_FEMALE = 'female'
GENDER_MIXED = 'mixed'
GENDER_CHOICES = [
    ('', 'Sin especificar'),
    (GENDER_MALE, 'Masculino'),
    (GENDER_FEMALE, 'Femenino'),
    (GENDER_MIXED, 'Mixto'),
]


def infer_gender_from_name(name: str) -> str:
    """Infiere el género desde un nombre libre de categoría/liga.

    Devuelve uno de GENDER_CHOICES o '' si no se reconoce. El orden importa:
    'femenino'/'femenina' contienen 'femin'; 'masculino'/'masculina' 'mascul';
    'mixto'/'mixta' 'mixt'. No se intenta detectar iniciales (M/F) por riesgo
    de falsos positivos.
    """
    if not name:
        return ''
    lowered = name.lower()
    if 'femen' in lowered:
        return GENDER_FEMALE
    if 'mascul' in lowered:
        return GENDER_MALE
    if 'mixt' in lowered:
        return GENDER_MIXED
    return ''
```

### 3.2. `Category` (`ilovevoley/core/models.py`)

```python
class Category(models.Model):
    # ... campos existentes ...
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Género / Rama',
        help_text='Vacío si la categoría es genérica (ej. "Senior").',
    )
```

### 3.3. `Organization` (`ilovevoley/core/models.py`)

```python
class Organization(models.Model):
    # ... campos existentes ...
    has_male_branch = models.BooleanField(
        default=True,
        verbose_name='Rama masculina activa',
        help_text='Recibir avisos de partidos masculinos.',
    )
    has_female_branch = models.BooleanField(
        default=False,
        verbose_name='Rama femenina activa',
        help_text='Recibir avisos de partidos femeninos.',
    )
    has_mixed_branch = models.BooleanField(
        default=False,
        verbose_name='Rama mixta activa',
        help_text='Recibir avisos de partidos mixtos.',
    )

    @property
    def active_branches(self) -> set:
        """Ramas que compite la organización, según sus booleanos."""
        branches = set()
        if self.has_male_branch:
            branches.add(GENDER_MALE)
        if self.has_female_branch:
            branches.add(GENDER_FEMALE)
        if self.has_mixed_branch:
            branches.add(GENDER_MIXED)
        return branches
```

### 3.4. `Team` (`ilovevoley/teams/models/teams.py`)

```python
class Team(models.Model):
    # ... campos existentes ...
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
        default='',
        verbose_name='Género / Rama',
        help_text='Vacío = hereda el género de la categoría.',
    )

    @property
    def effective_gender(self) -> str:
        """Género efectivo: el propio si está definido, si no el de la categoría."""
        if self.gender:
            return self.gender
        if self.category_id and self.category:
            return self.category.gender
        return ''
```

### 3.5. Servicio de ramas (`ilovevoley/competitions/services/branches.py`, nuevo)

```python
from django.db.models import Q

from ilovevoley.core.models import GENDER_FEMALE, GENDER_MALE, GENDER_MIXED


def match_branches(match) -> set:
    """Conjunto de ramas (géneros) implicadas en un partido.

    Toma el género de las categorías de la liga y el `effective_gender` de ambos
    equipos. Puede devolver conjunto vacío si nada está clasificado.
    """
    branches = set()
    if match.league_id:
        for category in match.league.categories.all():
            if category.gender:
                branches.add(category.gender)
    for team in (match.home_team, match.away_team):
        if team:
            gender = team.effective_gender
            if gender:
                branches.add(gender)
    return branches


def organization_branch_q(branches) -> Q | None:
    """Q que casa organizaciones con alguna de las ramas dadas.

    Devuelve None cuando `branches` está vacío: sin género conocido no se filtra
    (regla permisiva).
    """
    branches = set(branches)
    if not branches:
        return None
    q = Q()
    if GENDER_MALE in branches:
        q |= Q(has_male_branch=True)
    if GENDER_FEMALE in branches:
        q |= Q(has_female_branch=True)
    if GENDER_MIXED in branches:
        q |= Q(has_mixed_branch=True)
    return q
```

### 3.6. Filtrado de avisos (`ilovevoley/competitions/services/notifications.py`)

- **Push** (`notify_match_result`, `notify_match_change_push`, `notify_match_reminder`): tras construir el queryset `orgs = Organization.objects.filter(club_id__in=club_ids, ...)`, aplicar `q = organization_branch_q(match_branches(match))` y si `q is not None`, `orgs = orgs.filter(q)`.

- **Email de cambios** (`get_recipients_for_match`): extender la lógica existente de `_clubs_with_notifications_disabled` con un helper análogo que, por club, comprueba si **alguna** de sus organizaciones activas tiene activa alguna rama del partido. Un club cuyas orgs no cubren ninguna rama del partido se salta (como hoy con avisos desactivados). Los superusuarios no se filtran.

- **Suscripciones** (`users/tasks.py::notify_web_push_organization_task`): sin cambios. La rama ya se corta al seleccionar organizaciones; el filtrado por `CategoryPreference` se mantiene igual.

---

## 4. Migraciones y Backfill

1. **Esquema `core`** (`makemigrations`): `Category.gender`, `Organization.has_male_branch`, `Organization.has_female_branch`, `Organization.has_mixed_branch`.
2. **Esquema `teams`** (`makemigrations`): `Team.gender`.
3. **Datos `core`** (migración vacía + `RunPython`): recorrer `Category.objects.all()`, asignar `gender = infer_gender_from_name(category.name)` y guardar solo las que cambien. `reverse_code` = `migrations.RunPython.noop`.

Las migraciones se generan con `makemigrations`; el usuario las revisa y aplica.

---

## 5. Admin (única UI de configuración)

- `OrganizationAdmin` (`core/admin.py`): añadir las tres ramas a `fields`, `list_display` y `list_filter`.
- `CategoryAdmin` (`core/admin.py`): añadir `gender` a `list_display` y `list_filter`.
- `TeamAdmin` (`teams/admin/teams.py`): añadir `gender` a los fieldsets.

---

## 6. Pruebas y Criterios de Aceptación

1. **`infer_gender_from_name`** (`core`): `"Senior Femenino"`→female, `"Infantil Masculino"`→male, `"Alevín Mixto"`→mixed, `"Senior"`→'', `""`→''.
2. **`Category.gender` backfill** (patrón `users/tests/test_migrations.py`): tras migrar, una categoría `"Cadete Femenino"` queda en `female` y una `"Infantil"` en `''`.
3. **`Team.effective_gender`** (`teams`): propio definido gana; vacío hereda el de la categoría; sin categoría devuelve ''.
4. **Filtrado de avisos** (`competitions`):
   - Org con `has_female_branch=False` no recibe push de un partido femenino; con `True`, sí.
   - Partido sin género determinable (`match_branches` vacío) envía a la org aunque tenga las tres ramas en `False`.
   - Email de cambios: un club cuya org no cubre la rama del partido no aporta destinatarios; los superusuarios se mantienen.

Criterios de aceptación del issue cubiertos:
- Configuración de ramas activas en `Organization` (punto 3.3 y admin).
- Atributo/inferencia de género en `Category` y `Team` (puntos 3.2 y 3.4).
- Filtrado automático de avisos y suscripciones por ramas (punto 3.6).
