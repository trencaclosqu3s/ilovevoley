# Modelo Season y vinculación con vídeos, galería y plantillas

Fecha: 2026-09-20
Epic: #71

## Objetivo

Sustituir los strings de temporada dispersos por una única fuente de verdad
(`Season`) y vincular a ella ligas, vídeos, imágenes y roles de plantilla, de
forma que cada sección pueda filtrar por temporada y mostrar por defecto la
temporada activa.

## Modelo `Season`

`videosvoley/core/models.py`, tabla `videos_season`:

- `name`: nombre canónico (`2025-26`), único.
- `start_year` / `end_year`: periodo.
- `is_current`: temporada activa. Un `UniqueConstraint` condicional
  (`condition=Q(is_current=True)`) garantiza que solo haya una. Al guardar una
  temporada como activa se desmarcan las demás.
- `created_at`.

Helpers (`SeasonManager` y funciones de módulo):

- `normalize_season_name(raw)`: acepta `2025-26`, `2025-2026`, `2025/26`;
  devuelve `None` para valores vacíos o no reconocidos (`temp`).
- `season_start_year_for_date(value)`: corte el 1 de septiembre
  (sept–dic → año; ene–ago → año−1).
- `Season.objects.current()`: la activa o, si no hay, la más reciente.
- `Season.objects.for_date(value)` y `Season.objects.resolve(raw)`.

Es vocabulario **global/compartido** (como `Category`/`League`), sin FK a
`Organization`.

## Vinculaciones

| Modelo | Cambio | Migración |
| --- | --- | --- |
| `League` | `season` (CharField) → FK `Season` | `competitions/0005` |
| `Image` | `year` (IntegerField) → FK `Season` | `content/0004` |
| `Video` | FK `Season` nueva | `content/0004` |
| `PlayerRole` | FK `Season` nueva + constraints por temporada | `rosters/0005` |
| `StaffRole` | FK `Season` nueva + constraints por temporada | `rosters/0005` |

No se añade temporada a `Team` ni `Standing`: el equipo es persistente entre
temporadas y `Standing` cuelga de `League`. La temporada de una plantilla vive
en sus roles.

### Constraints de plantilla

- `unique_active_player_role`: `(person, team, season)` con `is_active=True`.
- `unique_jersey_number_per_team`: `(team, season, jersey_number)`.
- `unique_active_staff_role`: `(person, team, role, season)`.

Permiten que un mismo jugador/dorsal se repita entre temporadas, pero no dentro
de la misma.

## Migraciones de datos

- `League.season`: renombrado temporal, FK nueva, backfill normalizado y
  eliminación del campo string. Strings no reconocidos (`temp`) quedan `NULL`.
- `Image`/`Video`: temporada del partido (`match.league.season`) o, si no hay
  partido, inferida de la fecha de subida.
- `PlayerRole`/`StaffRole`: los roles existentes se asignan a la temporada
  anterior a la actual.

## Filtros de UI

Convención única, implementada en `core/season_utils.resolve_season_filter`:

- sin parámetro `season` → temporada activa;
- `?season=` vacío → todas las temporadas;
- `?season=<id>` → esa temporada (id inválido → temporada activa).

Aplicada en lista de vídeos, galería, plantilla de equipo, roster overview y
lista de equipos. Los contadores de plantilla se calculan por temporada.
