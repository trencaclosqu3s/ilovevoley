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
- **`Season.objects.current(for_date=None)`**: Devuelve la temporada activa.
  Se apoya en la regla del corte del 1 de septiembre (#448): si existe una
  temporada marcada con `is_current=True` cuyo periodo sigue vigente (o futuro,
  p.ej. activada manualmente con el wizard), se respeta. Si no hay ninguna marcada
  o la marcada quedó obsoleta tras superar el 1 de septiembre, resuelve la
  temporada correspondiente a la fecha de referencia y autoasigna atómicamente
  `is_current=True` (desmarcando la anterior). Las temporadas futuras creadas por
  scraping (`resolve`) se registran con `is_current=False` y no desplazan a la
  vigente antes de tiempo.
- **`Season.objects.resolve(raw)`**: Normaliza el string recibido y devuelve (creándola si no existe) la instancia de `Season`.
- **`Season.objects.for_date(value)`**: Devuelve la temporada correspondiente a la fecha indicada.

### Convención de Filtros de UI (`resolve_season_filter`)

La función `resolve_season_filter(request)` (`ilovevoley/core/season_utils.py`) estandariza el filtrado en todas las vistas (vídeos, galerías, clasificaciones, plantillas):

1. **Sin parámetro `season`** en la URL: Muestra la **temporada activa** (`current`).
2. **`?season=` (vacío)**: Desactiva el filtro y muestra **todas las temporadas**.
3. **`?season=<id>`**: Filtra por la temporada especificada (si el ID es inválido, hace fallback a la activa).

---

## 👥 Plantillas Deportivas (`ilovevoley.rosters`)

La app `rosters` separa la identidad física de las personas de los roles deportivos que desempeñan en cada temporada:

### 1. `Person`
Representa a una persona (jugador, entrenadora, delegado, fisioterapeuta) de forma persistente a lo largo de los años:
- **Campos**: Nombre, apellidos, `birth_date` / `birth_year`, foto, contacto (`email`, `phone`), `notes`, `user` (cuenta vinculada), `image_consent`, `is_provisional` y `organizations` (M2M a `Organization` a través de `PersonOrganization`, con estado de alta/baja por club, #478).
- **Identidad global (`unique_person_identity`)**: Desde #342 (sustituye la decisión A de #174) `Person` es global: la unicidad es `(first_name, last_name, birth_year)` en todos los clubes. Con `birth_year` NULL el constraint no aplica. `birth_year` es obligatorio en formularios (se deduce de `birth_date` si hay fecha).
- **Visibilidad por tenant**: Una ficha se ve en un club si está en `Person.organizations` (alta o adopción) o si tiene roles en un equipo del club (`Person.objects.for_tenant`). Si el alta choca con una ficha de otro club, el formulario ofrece «Añadir a mi club» (`person_adopt`, que exige nombre y año exactos). Contacto y notas solo para quien pueda editar (`can_edit_person`).
- **Fichas provisionales (#569)**: Las crea el acta (`ilovevoley/competitions/services/acta_roster.py`) con solo el apellido y `is_provisional=True`; el dorsal vive en su `PlayerRole`. El flag se limpia solo en `save()` al tener nombre y `birth_year`. Mientras siga provisional, el usuario puede reclamarla por id desde «Tú» (`person_link_claim`): son las únicas fichas que no se pueden verificar por nombre y año. Un manager del club puede descartar una creada por error (`person_provisional_discard`) si no tiene cuenta, familia, solicitud pendiente ni datos en otro club.

### 2. `PlayerRole`
Representa la ficha deportiva como jugador de un equipo en una temporada concreta:
- **`person`**: Clave foránea a `Person`.
- **`identity`**: Equipo, como `teams.TeamIdentity` (identidad estable del equipo entre temporadas, #428/#451), no `teams.Team`.
- **`season`**: Clave foránea a `Season`.
- **`jersey_number`**: Dorsal para esa temporada.
- **`position`**: Posición deportiva (colocador, receptor, opuesto, central, líbero, etc.).
- **`is_active`**: Estado del jugador en el equipo.
- **Constraints de integridad**:
  - `unique_active_player_role`: Una persona no puede tener dos fichas activas simultáneas en el mismo equipo durante la misma temporada (`person`, `identity`, `season`).
  - `unique_jersey_number_per_team`: El dorsal es único por equipo y temporada entre roles activos (`identity`, `season`, `jersey_number`).

### 3. `StaffRole`
Representa el rol en el cuerpo técnico para una temporada:
- **`person`**: Clave foránea a `Person`.
- **`identity`**: Equipo (`teams.TeamIdentity`).
- **`season`**: Clave foránea a `Season`.
- **`role`**: Función técnica (primer entrenador, asistente, delegado, fisioterapeuta, etc.).
- **`is_active`**: Estado del rol.
- **Soporte multi-rol**: Una misma persona puede desempeñar múltiples roles en el mismo equipo (ej: primer entrenador y delegado) gracias al constraint `unique_active_staff_role` que evalúa `(person, identity, role, season)` entre roles activos.

Los roles pertenecen al club de su equipo (`PersonRoleTenantQuerySet`). La vista «Tú» (`rosters:my_profile`) agrega los roles del usuario en todos los clubes.

### 4. `PersonLinkRequest` (#531)
Vínculo cuenta ↔ ficha self-service. El usuario pide enlazar su ficha (`kind=self`) o la de un hijo/a (`kind=child`) identificándola por nombre, apellidos y año exactos (`ilovevoley/rosters/link_requests.py`). Un moderador del club la resuelve en `/core/moderacion/`; aprobar (`approve_link_request`) es lo único que escribe `Person.user` o `User.children`. Solo una solicitud pendiente por (usuario, ficha) (`unique_pending_person_link_request`).

### 5. `SeasonWrapped` (#458)
Resumen de temporada por persona, temporada y modalidad (`unique_wrapped_per_season_modality`), congelado al cierre en `stats`. Lo genera la tarea `generate_season_wrappeds` (acciones de `SeasonAdmin`, con o sin aviso a jugadores); es idempotente y una corrección de acta posterior exige borrar la fila y relanzar. Las fotos se filtran por consentimiento al mostrar, no al congelar; el rival es el equipo, nunca un jugador; colores y escudo salen del club del rol de esa temporada (`season_organization`), no del dominio. El texto lo redacta un LLM en `redact_pending_wrapped_narratives` (#551, solo con `LLM_NARRATIVE_ENABLED`).

---

## 🔗 Vinculación Transversal con otros Dominios

- **Competiciones (`competitions.League`)**: Cada liga está vinculada a una `Season` mediante ForeignKey. Las clasificaciones y calendarios se consultan y filtran por temporada.
- **Contenidos (`content.Video` y `content.Image`)**:
  - Al asociar un vídeo o foto a un partido, heredan automáticamente la temporada de la liga del partido (`match.league.season`).
  - Para contenidos sin partido vinculado, la temporada se infiere de la fecha de subida o creación.
  - La galería y lista de vídeos filtran por defecto por la temporada activa para evitar mezclar material histórico con la temporada en curso.
