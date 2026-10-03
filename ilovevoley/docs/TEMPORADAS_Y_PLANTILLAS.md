# Sistema de Temporadas y Plantillas Deportivas

Este documento explica el modelo unificado de temporadas (`Season`) y la gestión de plantillas deportivas (`rosters`) por temporada en I Love Voley.

## 📅 Modelo `Season` (`ilovevoley.core.models.Season`)

El modelo `Season` actúa como **fuente única de verdad** para las temporadas deportivas en toda la plataforma:

- **`name`**: Nombre canónico en formato `YYYY-YY` (ej: `2025-26`). Único.
- **`start_year`**: Año de inicio (ej: `2025`).
- **`end_year`**: Año de fin (ej: `2026`).
- **`is_current`**: Booleano que marca la temporada activa actual. Un `UniqueConstraint` condicional (`is_current=True`) garantiza que solo pueda existir una temporada activa simultáneamente; al marcar una temporada como activa, el resto se desmarcan de forma atómica.

### Helpers y Utilidades

- **`normalize_season_name(raw)`**: Convierte variantes como `2025-26`, `2025-2026` o `2025/26` al formato canónico `2025-26`. Devuelve `None` para entradas inválidas.
- **`season_start_year_for_date(value)`**: Determina el año de inicio de temporada a partir de una fecha arbitraria, usando el corte estándar federativo del **1 de septiembre** (septiembre–diciembre pertenece a la temporada iniciada en ese año; enero–agosto pertenece a la temporada iniciada el año anterior).
- **`Season.objects.current()`**: Devuelve la temporada marcada como activa, o en su defecto la más reciente por año de inicio.
- **`Season.objects.resolve(raw)`**: Normaliza el string recibido y devuelve (creándola si no existe) la instancia de `Season`.
- **`Season.objects.for_date(value)`**: Devuelve la temporada correspondiente a la fecha indicada.

### Convención de Filtros de UI (`resolve_season_filter`)

La función [`resolve_season_filter(request)`](file:///Users/jamartinmari/PycharmProjects/videosvoley/ilovevoley/core/season_utils.py) estandariza el filtrado en todas las vistas (vídeos, galerías, clasificaciones, plantillas):

1. **Sin parámetro `season`** en la URL: Muestra la **temporada activa** (`current`).
2. **`?season=` (vacío)**: Desactiva el filtro y muestra **todas las temporadas**.
3. **`?season=<id>`**: Filtra por la temporada especificada (si el ID es inválido, hace fallback a la activa).

---

## 👥 Plantillas Deportivas (`ilovevoley.rosters`)

La app `rosters` separa la identidad física de las personas de los roles deportivos que desempeñan en cada temporada:

### 1. `Person`
Representa a una persona (jugador, entrenadora, delegado, fisioterapeuta) de forma persistente a lo largo de los años:
- **Campos**: Nombre, apellidos, alias, fecha de nacimiento, foto de perfil, y `organization` (club al que pertenece la ficha).
- **Identidad Única por Club (`unique_person_identity`)**: Siguiendo la decisión de arquitectura #174, la unicidad evalúa `(organization, first_name, last_name, birth_date)`, no de forma global. Esto permite que una misma persona física pueda tener ficha deportiva en dos clubes diferentes (ej. entrenar en un club y jugar en otro). Las fichas legadas con `organization=NULL` comparten su propio grupo (`nulls_distinct=False`).
- **Formularios**: Al instanciar formularios de personas se debe pasar siempre el tenant activo (`PersonForm(..., organization=request.tenant)`) para que la validación se realice contra el club correspondiente.

### 2. `PlayerRole`
Representa la ficha deportiva como jugador de un equipo en una temporada concreta:
- **`person`**: Clave foránea a `Person`.
- **`team`**: Equipo federativo (`teams.Team`).
- **`season`**: Clave foránea a `Season`.
- **`jersey_number`**: Dorsal para esa temporada.
- **`position`**: Posición deportiva (colocador, receptor, opuesto, central, líbero, etc.).
- **`is_active`**: Estado del jugador en el equipo.
- **Constraints de integridad**:
  - `unique_active_player_role`: Una persona no puede tener dos fichas activas simultáneas en el mismo equipo durante la misma temporada.
  - `unique_jersey_number_per_team`: El dorsal es único por equipo y temporada (distintos jugadores pueden usar el mismo dorsal en temporadas diferentes).

### 3. `StaffRole`
Representa el rol en el cuerpo técnico para una temporada:
- **`person`**: Clave foránea a `Person`.
- **`team`**: Equipo federativo.
- **`season`**: Clave foránea a `Season`.
- **`role`**: Función técnica (primer entrenador, asistente, delegado, fisioterapeuta, etc.).
- **`is_active`**: Estado del rol.
- **Soporte multi-rol**: Una misma persona puede desempeñar múltiples roles en el mismo equipo (ej: primer entrenador y delegado) gracias al constraint `unique_active_staff_role` que evalúa `(person, team, role, season)`.

---

## 🔗 Vinculación Transversal con otros Dominios

- **Competiciones (`competitions.League`)**: Cada liga está vinculada a una `Season` mediante ForeignKey. Las clasificaciones y calendarios se consultan y filtran por temporada.
- **Contenidos (`content.Video` y `content.Image`)**:
  - Al asociar un vídeo o foto a un partido, heredan automáticamente la temporada de la liga del partido (`match.league.season`).
  - Para contenidos sin partido vinculado, la temporada se infiere de la fecha de subida o creación.
  - La galería y lista de vídeos filtran por defecto por la temporada activa para evitar mezclar material histórico con la temporada en curso.
