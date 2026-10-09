# Plantilla por identidad y temporada

- **Issue:** #447 (diseño, sin código)
- **Fecha:** 2026-10-08
- **Estado:** propuesta, pendiente de revisión
- **Relacionadas:** #444, #445, #446 (PR #449), #448 (`Season.is_current`)

## 1. Problema

`Team` es una **aparición federativa**: `federation_id` es único y cada fase o
competición (liga regular, oro/plata, Campeonato de Mallorca, de Baleares…) trae
un id nuevo y, por tanto, una fila nueva de `Team`. `PlayerRole` y `StaffRole`
cuelgan de `Team`, así que:

- cada fase nueva arranca con la plantilla vacía;
- la plantilla de una misma temporada acaba repartida, o duplicada, entre filas;
- el paso de una temporada a otra es manual.

`TeamIdentity` (#428) ya representa al equipo a lo largo del tiempo: sin
temporada propia ni nombre fijo (el patrocinio cambia), único por
`(club, categoría, género, core_name_normalized)`. Un mismo club puede tener dos
plantillas de la misma categoría y género a la vez si tienen identidades con
distinto `core_name`.

## 2. Medidas en producción (2026-10-08, solo lectura)

| Medida | Valor |
|---|---|
| `PlayerRole` totales / activos / sin temporada | 49 / 49 / 0 |
| `StaffRole` totales / activos / sin temporada | 6 / 6 / 0 |
| Equipos sin identidad | 43, de los que 42 no tienen club, 15 no tienen categoría y **ninguno tiene roles** |
| Identidades con `club` nulo | 0 |
| Misma persona en dos filas de la misma (identidad, temporada) | 12, todas en la identidad 35, temporada 2025-26, equipos 48 y 10, con **el mismo dorsal**; solo la persona 20 tiene posición distinta (central en 48, colocadora en 10, que es la última: cambió de posición durante la temporada) |
| Dorsal repetido con personas distintas al unificar | 0 |
| `StaffRole` repetido al unificar (persona, rol) | 2, en la identidad 35, equipos 48 y 10 |
| Rol inactivo que chocaría con uno activo al unificar | 0 |
| Equipos cuyo club no coincide con el de su identidad | 4 (ids 82, 109, 68 sin club; 190, Pórtol), todos sin roles |

Las 12 duplicidades son justo el síntoma que motiva la issue: la plantilla del
Infantil 2025-26 se metió dos veces, una en cada aparición (equipos 10 y 48).

### Identidades con más de una fila activa

| Identidad | Filas (id: nombre, activa) | Roles |
|---|---|---|
| 2 | 33 ALARO VOLEI SES PLANES (sí), 160 ALARO VOLEI CLINICA DENTAL (sí) | 0 |
| 7 | 12 ALCOCEBA… CV PORTOL (sí), 89 Club Voleibol Pórtol (sí), 192 MPT CV. PORTOL NEGRO (sí) | 0 |
| 14 | 16 TECNOJARDI ALGAIDA VC (sí), 85 Algaida Volei Club (sí) | 0 |
| 22 | 88 Club Volei Maó (sí), 99 CLUB VOLEI MAO ALEVI MASCULI (sí) | 0 |
| 35 | 10 CV SANT JOSEP GROC (sí, 12 jugadores en 2025-26), 48 (no, 13 en 2025-26), 52 LILA (no, 0), 54 CV SANT JOSEP (sí, 2 en 2026-27) | 25 + 2 |
| 38 | 19 CV. PORTOL ROJO (sí), 190 CONTINIA SOFTWARE CMVP PORTOL ROJO (sí) | 0 |
| 47 | 18 VOLEY CIDE PALMA (sí), 90 Club Voleibol Cide (sí) | 0 |

## 3. Decisión

### 3.1 Modelo

`PlayerRole.team` y `StaffRole.team` **se sustituyen** por
`identity = ForeignKey(TeamIdentity, on_delete=PROTECT, related_name=...)`. No
conviven: una sola fuente de verdad. `season` ya existe y es obligatoria de
hecho (0 roles sin temporada).

La **plantilla** de un equipo es `roles(identity=X, season=S)`. No es un modelo
nuevo: es una consulta.

Las constraints pasan a usar la identidad:

| Antes | Después |
|---|---|
| `PlayerRole (person, team, season)` activo único | `(person, identity, season)` activo único |
| `PlayerRole (team, season, jersey_number)` activo único | `(identity, season, jersey_number)` activo único |
| `StaffRole (person, team, role, season)` activo único | `(person, identity, role, season)` activo único |

`Meta.ordering`, los índices `(team, is_active)` y `__str__` pasan a `identity`
(`identity.core_name`).

`on_delete=PROTECT` para que borrar una identidad con plantilla falle en vez de
arrastrarla. Hoy `PlayerRole.team` es `CASCADE`, así que borrar una aparición
federativa borra sus roles; con el cambio, borrar un `Team` deja de tocar la
plantilla.

### 3.2 `Team` sin identidad

`Team.identity` **sigue siendo nullable**. Esto corrige la respuesta inicial
("crear la identidad en la migración para los 43"), porque las medidas muestran
que:

- 42 de esos 43 no tienen club, y `create_identity_for_team` necesita club y
  categoría para dar una identidad única: crearlas generaría identidades
  huérfanas, sin restricción de unicidad (`condition=club__isnull=False`);
- ninguno tiene roles, así que la migración no los necesita.

La regla pasa a ser: **solo puede tener plantilla un equipo con identidad**.
Dar de alta un rol desde un equipo sin identidad la resuelve antes con
`resolve_team_identity` (el mismo camino que usa el scraping), y si no se puede
resolver (falta club o categoría), lo rechaza con un error de formulario.

### 3.3 `Match`, lineups, convocatorias y clasificación

**Siguen colgando de `Team`.** Son hechos de una aparición federativa (un
partido se juega en una fase concreta) y `federation_id` es la clave de scraping.

La plantilla de un partido se resuelve así:
`match.home_team.identity` + `match.league.season` → `roles(identity, season)`.

- `competitions/services/lineups.py::_roles_lookup`: el mapa sigue indexado por
  `(team_id, jersey)` hacia fuera, pero se rellena con los roles de
  `(team.identity, season)` de cada equipo del partido. Un equipo sin identidad
  no tiene plantilla, igual que hoy uno sin roles.
- `competitions/services/callup_matcher.py`: `player_roles__season=...` sobre
  `Team` pasa a `identity__player_roles__season=...`, y
  `[r.team for r in person.player_roles...]` pasa a los equipos de las
  identidades del jugador que juegan esa temporada (`identity.teams`).
- `competitions/views.py` (acta enriquecida), `services/notifications.py`
  (staff a notificar, jugador convocado) y `content/services.py` (etiquetado):
  mismo cambio, `team__in=` → `identity__teams__in=` o
  `identity=team.identity`.
- `Standing` no usa roles: no cambia.

### 3.4 Aislamiento por tenant

`PersonRoleTenantQuerySet.tenant_filter` pasa de
`Q(team__in=Team.objects.for_tenant(t))` a
`Q(identity__teams__in=Team.objects.for_tenant(t))`. Así se conserva la
semántica actual (el rol pertenece al club de su equipo, incluido el casamiento
por nombre de `TeamTenantQuerySet`). El join puede duplicar filas: se acota por
`pk__in`, igual que `PersonTenantQuerySet.for_tenant`. Lo mismo para
`core/tenancy.py:56-57` (`player_roles__identity__teams__in`).

Se descarta filtrar por `identity.club`: dejaría fuera los equipos que hoy
entran en el tenant por nombre y no por FK.

### 3.5 Fusión y reasignación de identidades

Ahora la plantilla vive en la identidad, así que:

- **Reasignar un `Team` a otra identidad** (admin, `assign_identity`) no mueve
  roles: el equipo pasa a mostrar la plantilla de su nueva identidad. Es el
  comportamiento buscado.
- **Fusionar identidades** (`TeamIdentityCandidate.accept`, que mueve todos los
  equipos de la identidad vieja a la sugerida, y `assign_common_identity`) deja
  la identidad vieja sin equipos pero con sus roles. Estas rutas **tienen que
  mover también los roles**, y deduplicarlos con la misma regla que la
  migración (§4), en la misma transacción. Si no, la plantilla se queda
  huérfana e invisible.

### 3.6 Identidades con varias filas activas

En el modelo nuevo, varias filas activas en una identidad **son lo normal**: un
equipo juega varias competiciones a la vez y todas comparten plantilla. El
"¿cuál es la fila vigente?" deja de importar para la plantilla, y
`Team.is_active` vuelve a significar solo "sigue compitiendo".

- **35** (Sant Josep Infantil): la agrupación es legítima (Groc = liga,
  Lila = Campeonato de Baleares, sin color = esta temporada). La migración
  deduplica los 12 jugadores y los 2 técnicos repetidos.

Un jugador con posiciones distintas en **dos identidades** del mismo club en
la misma temporada (central en el infantil, líbero en el cadete) no es un
conflicto: son dos roles en dos plantillas distintas.
- **2, 7, 14, 22, 38, 47**: son de otros clubes y no tienen roles, así que no
  afectan a la migración. Sí conviene revisar en el admin la **7**: agrupa
  "MPT CV. PORTOL NEGRO" mientras "PORTOL ROJO" tiene identidad propia (38), y
  el club del equipo 190 (47) no coincide con el de su identidad (30). Es
  limpieza de datos, no un bloqueo.

### 3.7 Pantallas

- `teams:team_roster` (URL por `Team`) muestra `roles(team.identity, season)`
  con la temporada de `resolve_season_filter(request)`. La URL no cambia.
- El alta masiva de #446 escribe en `team.identity` en lugar de en `team`.
  "Copiar de la temporada anterior" se simplifica a
  `roles(identity, season_anterior)`: desaparece la búsqueda por "cualquier
  `Team` con la misma identidad, gana el más reciente".
- `PlayerRoleForm` y `StaffRoleForm` siguen eligiendo un **equipo** (es lo que
  reconoce el usuario) y guardan `identity=team.identity`. Validación: el
  equipo debe tener identidad (§3.2) y el dorsal no puede chocar en
  `(identity, season)`.
- Ficha de persona, "Tú" y listado de personas: `role.team.*` pasa a
  `role.identity.*` (nombre, categoría). Para enlazar a la plantilla se usa la
  fila activa más reciente de la identidad.

### 3.8 `Season.is_current`

Fuera del alcance de esta issue: se decide en **#448**. Este diseño solo
necesita "la temporada del filtro" (`resolve_season_filter`) y "la temporada de
la liga del partido", que no dependen de esa decisión.

## 4. Plan de migración

Tres migraciones generadas con `makemigrations`; la de datos se crea con
`--empty` y `RunPython`.

1. **Esquema A**: añade `identity` nullable a `PlayerRole` y `StaffRole`.
2. **Datos** (`RunPython`, con reverse que rellena `team` con la fila activa
   más reciente de la identidad):
   1. Si algún rol tiene un equipo sin identidad, **aborta** con un error que
      liste los ids (hoy son 0; mejor fallar que perder roles).
   2. `identity = team.identity` para todos los roles.
   3. Deduplica por `(identity, season, person)` en jugadores y por
      `(identity, season, person, role)` en técnicos. Se conserva un rol por
      grupo: el activo y, entre activos, el de `updated_at` más reciente, con
      el id mayor como desempate. Los demás se borran.
      **Gana el último estado**: que un jugador cambie de posición, o incluso de
      dorsal, entre fases de la misma temporada es normal (empezar de central y
      acabar de colocador), y el rol guarda una sola posición, la última. Se
      pierde la anterior; es una decisión aceptada. Hoy pasa en un caso: la
      persona 20 era central en el equipo 48 (editado el 2025-10-13) y colocadora
      en el 10 (2026-05-31), y se queda con colocadora.
   4. Comprueba que no quedan dorsales repetidos con personas distintas en
      `(identity, season)`, y si los hay aborta listando los ids (hoy son 0).
3. **Esquema B**: quita las constraints viejas y el campo `team`, pone
   `identity` no nula y añade las constraints nuevas.

Con 49 + 6 filas, el coste es despreciable. Hay que aplicarla con `--create-db`
en los tests.

## 5. Inventario de referencias

Unas 260 referencias en 35 ficheros, contando los tests. Las de código de
producto se agrupan así:

| Zona | Ficheros | Cambio |
|---|---|---|
| Modelo | `rosters/models/rosters.py` (FKs, constraints, `get_player_roles`, `get_all_active_teams`, `__str__`) | FK → identity; `get_all_active_teams` pasa por `identity__teams` |
| Tenancy | `core/tenancy.py` (`PersonTenantQuerySet`, `PersonRoleTenantQuerySet`), `core/tenant_utils.py:311` | §3.4 |
| Formularios | `rosters/forms.py` (validación de duplicado y dorsal) | §3.7 |
| Vistas de personas | `rosters/views.py` (listado, ficha, "Tú", alta/edición/baja de roles; ~35 refs) | `team__in=tenant_teams` → filtro por tenant del queryset; `select_related('identity__category')` |
| Vistas de equipo | `teams/views.py` (listado con conteos, `team_roster`) | `team.player_roles` → `PlayerRole.objects.filter(identity=team.identity, season=...)` |
| Partidos | `competitions/services/lineups.py`, `callup_matcher.py`, `notifications.py`, `competitions/views.py:1104` | §3.3 |
| Contenido | `content/services.py:124` (etiquetado por plantilla) | `identity__teams__in` |
| Admin | `rosters/admin/rosters.py` (inlines, list_filter por team), `teams/admin/teams.py:180-185` (conteos) | Conteos por `obj.identity`; filtro del admin por identidad |
| Fusión de identidades | `teams/models/teams.py::TeamIdentityCandidate.accept`, `teams/identity.py::assign_common_identity` | §3.5 |
| Plantillas | `rosters/templates/rosters/{my_profile,person_detail,person_list}.html` (16 accesos a `role.team.*`), `teams/templates/teams/team_roster.html` | `role.identity.*` |
| Legado | `videos/models`, `videos/forms` (re-exports) | Ninguno, si solo re-exportan |
| Tests | `rosters/tests`, `teams/tests`, `competitions/tests/{test_lineups,test_callup_matcher,test_notifications,test_branch_notifications}`, `core/tests/{test_tenancy,test_protected_media,test_cross_tenant_access}`, `content/tests/test_tagging` | Las fixtures crean roles con `team=` y pasan a `identity=` |

Tests nuevos que se justifican según la guía:

- la migración de datos deduplica conservando el rol correcto (transformación no
  trivial, y fue la causa del problema);
- la plantilla de un partido se resuelve por identidad aunque el partido sea de
  otra fase (regla de negocio central del cambio);
- fusionar identidades mueve y deduplica los roles (efecto persistente con
  pérdida de datos si falla);
- un rol de un equipo de otro club no entra en el tenant (ya existe en
  `test_cross_tenant_access`: se adapta, no se duplica).

## 6. Alternativas descartadas

### 6.1 Resolver solo a nivel de pantalla

Consiste en no tocar el modelo: los roles siguen en cada fila de `Team` (una
por fase) y la pantalla de plantilla junta los roles de todas las filas de la
identidad para mostrarlos. No es un flujo de revisar y aceptar: solo cambia la
lectura. Es lo que hace hoy #446 como paso intermedio al copiar la temporada
anterior.

Se descarta como solución final porque:

- las constraints siguen siendo por `Team`, así que nada impide meter la misma
  plantilla dos veces en dos apariciones (en producción hay 12 jugadores y 2
  técnicos duplicados exactamente así);
- cada consumidor (lineups, convocatorias, notificaciones, etiquetado, tenancy)
  tendría que repetir la agregación;
- obliga a elegir "la fila vigente" cuando hay varias activas, y no hay un
  criterio estable para hacerlo.

### 6.2 Fusionar filas de `Team` al scrapear

Consistiría en reutilizar una sola fila de `Team` para todas las fases.

Se descarta porque:

- rompe `federation_id` único, que es la clave con la que el scraping casa
  partidos y clasificaciones de cada fase;
- no arregla el histórico: las filas ya repartidas siguen existiendo;
- mezcla en una fila hechos que son de cada fase (nombre con patrocinio,
  liga, clasificación) y perdería la distinción entre colores o variantes.

Ambas alternativas se descartaron el 2026-10-08.

## 7. Issues de implementación derivadas

1. **#451 — Plantilla por identidad y temporada: modelo, migración y
   consultas.** Cubre §3.1–3.5, §3.7, §4 y §5 en un solo PR: quitar
   `PlayerRole.team` obliga a adaptar a la vez todos los consumidores.
   Depende de que #449 (alta masiva) esté integrada, para adaptar su código en
   vez de rehacerlo.
2. **#452 — Revisar la identidad 7 (Pórtol Negro) y los clubes discordantes.** Limpieza de datos en el admin, sin código.

#448 (`Season.is_current`) es independiente y se lleva por separado.
