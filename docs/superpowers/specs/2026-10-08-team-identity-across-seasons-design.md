# Identidad estable de equipo entre temporadas

**Fecha:** 2026-10-08  
**Estado:** Spec aprobado; plan en `docs/superpowers/plans/2026-10-08-team-identity-across-seasons.md`  
**Issue:** [#428](https://github.com/trencaclosqu3s/ilovevoley/issues/428)  
**Apps afectadas:** `ilovevoley.teams`, `ilovevoley.competitions` / capa de scraping en `ilovevoley.videos.scraping`

---

## 1. Contexto y problema

Hoy `Team.federation_id` (único) se genera a partir del id de la liga y otras concatenaciones. El mismo equipo real aparece como filas distintas cada temporada (p. ej. Sant Josep Infantil con id distinto año a año). Un cambio de patrocinador («Alaró Clínica Dental» → «Alaró Construcciones Niu») también tiende a crear un equipo «nuevo».

Sin identidad estable no hay histórico continuo por equipo (clasificaciones, plantillas, partidos) a ojos del usuario.

El diseño de `Season` (#71) asumía que `Team` era persistente entre temporadas. En la práctica el scrape genera apariciones nuevas; esta feature introduce una entidad de identidad y deja las filas `Team` como apariciones federativas (con su `federation_id` y su nombre de entonces).

`parent_team` / `variant_*` cubren variantes (A/B, color vinculadas). **No** se reutilizan para el cambio entre años.

---

## 2. Decisiones de arquitectura

1. **Enfoque A — Identidad + apariciones.** Nueva entidad `TeamIdentity` que agrupa filas `Team`. `federation_id` sigue siendo id de aparición federativa y **no** es la identidad.
2. **No reutilizar filas por nombre para «robar» `federation_id`.** Si el `federation_id` es nuevo, se crea una fila `Team` nueva y se resuelve la identidad por separado.
3. **Sesgo conservador.** Ante la duda, enlace **manual** (`TeamIdentityCandidate`). Preferible trabajo a mano que un enlace incorrecto (p. ej. Portol Rojo ≠ Portol Negro ≠ Portol Blanco en la misma categoría).
4. **Auto-enlace solo con match exacto** de `core_name_normalized` (mismo club + categoría + género efectivo). Fuzzy solo genera candidatas.
5. **Nombre histórico en UI.** En ligas/partidos/clasificaciones de una temporada concreta se muestra `Team.name` de esa aparición. La identidad aporta el hilo histórico, no sustituye la etiqueta federativa de entonces.
6. **Confirmación y aviso** al estilo `LeagueCandidate`: admin + email a `TECHNICAL_ALERT_EMAILS`.
7. **Backfill** vía migración `RunPython` en `teams`: agrupa exactos; casi-duplicados → candidatas pendientes. No fusiona ni borra filas `Team`.

---

## 3. Modelo de datos

### 3.1. `TeamIdentity` (`ilovevoley.teams`)

| Campo | Tipo | Notas |
| --- | --- | --- |
| `club` | FK → `Club`, null=True | Preferible relleno para auto-match; sin club no hay auto-enlace |
| `category` | FK → `Category` | |
| `gender` | CharField, `GENDER_CHOICES` | Vacío = hereda de categoría (misma semántica que `Team`) |
| `core_name` | CharField | Nombre canónico **sin patrocinador**; **con** color/letra de equipo |
| `core_name_normalized` | CharField, db_index | Clave de matching |
| `created_at` | DateTimeField | auto_now_add |

**Unique:** `(club, category, gender, core_name_normalized)` cuando `club` no es null. Equipos sin club quedan fuera del auto-match hasta resolver club.

Al crear la identidad se materializa en `gender` el género efectivo usado para el match (el del equipo o, si vacío, el de la categoría), para que la clave unique no dependa de una property.

### 3.2. `Team` (cambio mínimo)

- Nuevo FK `identity` → `TeamIdentity`, `null=True`, `related_name='teams'`, `on_delete=PROTECT`.
- `federation_id` sigue único; no se reescribe en apariciones anteriores al actualizar la actual.
- `parent_team` / `variant_*` sin cambios de semántica.
- `name` / `sponsor_name` viven en la aparición.

### 3.3. `TeamIdentityCandidate`

| Campo | Tipo | Notas |
| --- | --- | --- |
| `new_team` | FK → `Team` | Aparición scrapeada / nueva |
| `suggested_identity` | FK → `TeamIdentity`, null=True | Editable en admin si hay que corregir |
| `suggested_team` | FK → `Team`, null=True | Aparición previa de referencia para la UI |
| `score` | FloatField, null=True | Similitud si aplica |
| `reason` | CharField/TextField | Motivo corto legible |
| `status` | `pending` \| `approved` \| `rejected` | default `pending`, db_index |
| `created_at` | DateTimeField | |

**Aprobar:** `new_team.identity = suggested_identity` (o la elegida en admin); status `approved`.  
**Rechazar:** crear `TeamIdentity` nueva para `new_team` y enlazarla; status `rejected` («no es el de antes»).

No hay merge destructivo de PKs de `Team` (partidos/plantillas no se reasignan en masa).

---

## 4. Normalización de nombre (`core_name`)

### Entra en la identidad (no se elimina)

- Color / letra de equipo: Rojo, Negro, Blanco, Groc, Lila, A, B, etc.
- Cualquier token que distinga equipos del mismo club en la misma categoría.

### Se elimina solo con señal clara de patrocinio

- Valor de `sponsor_name` o campos federativos `E*PAT` / equivalentes.
- Sufijo o fragmento que **coincida** con ese sponsor.
- Sin esa señal: **no** recortar el nombre a ciegas.

La normalización reutiliza/extiende `normalize_team_name` (`ilovevoley.videos.utils`) tras el strip de sponsor seguro. El helper de extracción de `core_name` vive en `teams` (o módulo compartido mínimo) para usarlo desde scrape y backfill.

---

## 5. Matching en el scrape

Punto de enganche principal: `FederationScraper.update_teams` (y cualquier camino que cree `Team`).

1. **Hit por `federation_id`** → reutilizar esa fila `Team`. No inventar identidad aquí salvo alta primera vez sin identidad (crear identidad propia si falta).
2. **Sin hit** → **no** buscar otra fila por nombre para reasignar `federation_id`. Crear `Team` nuevo.
3. **Resolver identidad** entre identidades (o apariciones ya enlazadas) del mismo `club` + `category` + género efectivo:
   - **Exacto** (`core_name_normalized`) → enlazar a esa `TeamIdentity`. Sin candidata.
   - **Duda** (similitud alta pero no exacta, o varios candidatos) → `TeamIdentityCandidate` pendiente; `new_team.identity = NULL` hasta decisión manual.
   - **Ninguno** → crear `TeamIdentity` nueva y enlazar.
4. **Club distinto** → nunca auto-enlazar (misma idea que `_is_other_club`).
5. **Variantes** (`parent_team`) → no mezclar con la dimensión de identidad entre años; matching de identidad entre raíces (o misma identidad en el árbol de variantes tras backfill).
6. Actualizar `name` / `sponsor_name` solo en la aparición actual; no mutar otras filas de la misma identidad.

Al crear candidatas nuevas en un scrape: al final de esa ejecución, si se creó al menos una candidata nueva, email a `get_technical_alert_emails()` (misma operativa que `discover_leagues_task`), plantilla gemela de `emails/league_candidates_pending.html`, enlace al changelist admin con `?status__exact=pending`.

---

## 6. Nombre histórico en UI

| Contexto | Qué se muestra |
| --- | --- |
| Liga / partido / clasificación de una temporada concreta | `Team.name` (y sponsor si aplica) de **esa** aparición |
| Ficha de histórico agregado / identidad | `TeamIdentity.core_name` + lista de apariciones con nombre por contexto |
| Temporada actual | Nombre de la aparición actual |

Partidos y standings siguen apuntando al `Team` de esa competición. La continuidad de producto se consulta vía `identity`.

---

## 7. UI de confirmación y email

- Django admin (Unfold) de `TeamIdentityCandidate`, filtro `pending`.
- Listado: equipo nuevo (nombre, club, categoría, `federation_id`) · identidad sugerida · aparición previa · motivo/score.
- Acciones aprobar / rechazar (y edición de `suggested_identity` antes de aprobar).
- Email operativo copiado de ligas candidatas (`discover_leagues_task`): subject traducible, `send_notification_email`, solo destinatarios técnicos, CTA al admin.
- Sin pantalla tenant-facing en este alcance.

---

## 8. Backfill (`RunPython` en `teams`)

1. Solo equipos con `club` + `category`; el resto queda `identity=NULL`.
2. Agrupar por `(club_id, category_id, gender efectivo, core_name_normalized)` con la misma normalización conservadora del scrape.
3. Un grupo → una `TeamIdentity`; todas las filas del grupo se enlazan. `core_name`: el más limpio del grupo (sin sponsor si hay señal; si no, el más representativo).
4. Grupo de un solo equipo → identidad propia.
5. Casi-duplicados (similitud alta, no exacta) → **no** fusionar; crear `TeamIdentityCandidate` pendientes.
6. Variantes: el root define/ comparte identidad; variantes del mismo árbol reciben la misma `identity`.
7. Idempotente: si `identity` ya está asignada, no tocar.
8. No borrar ni fusionar filas `Team`; no reescribir `federation_id`.

---

## 9. Alcance y fuera de alcance

### En alcance

- Modelos `TeamIdentity`, `TeamIdentityCandidate`, FK en `Team`.
- Matching conservador en scrape + cese del reuse de `federation_id` por nombre.
- Admin + email de candidatas.
- Backfill `RunPython`.
- Tests que protejan: auto-enlace exacto; no auto-enlace Portol Rojo/Negro; candidata en duda; nombre histórico intacto al actualizar aparición nueva; backfill exacto vs fuzzy.

### Fuera de alcance (este issue)

- Pantalla de histórico de equipo en front tenant (se puede seguir con listados actuales; la ficha agregada puede ser follow-up).
- Merge destructivo de PKs / reasignación masiva de partidos y roles.
- Cambiar semántica de `parent_team` / variantes.
- Añadir `season` a `Team`.
- Recorte heurístico agresivo de patrocinadores sin señal federativa.

---

## 10. Criterios de aceptación (mapeo #428)

- [ ] Equipo de temporada nueva se vincula automáticamente al equivalente anterior cuando coincide con claridad (mismo club + categoría/género + `core_name` exacto sin patrocinador).
- [ ] Si hay duda, se propone el vínculo en confirmación de un clic; nunca se enlaza a ciegas (ni en backfill fuzzy).
- [ ] Cambio de patrocinador o de `federation_id` no crea un equipo «nuevo» a ojos del usuario cuando el match es exacto (misma identidad; apariciones distintas OK).
- [ ] Colores/letras del mismo club+categoría son identidades distintas.
- [ ] En contexto de liga/partido pasado se ve el nombre de entonces.
- [ ] Backfill de equipos existentes vía `RunPython`.
- [ ] Aviso email a técnicos cuando hay candidatas nuevas (operativa análoga a ligas).

---

## 11. Archivos previstos (orientativo)

- `ilovevoley/teams/models/teams.py` — modelos y FK.
- `ilovevoley/teams/admin/` — admin de identidad y candidatas.
- `ilovevoley/teams/services/` (o equivalente mínimo) — `core_name` + resolución de identidad.
- `ilovevoley/videos/scraping/federation.py` — `update_teams`.
- Plantilla `emails/team_identity_candidates_pending.html`.
- Migraciones `teams` (schema + `RunPython`).
- Tests en `ilovevoley/teams/tests/` y ajuste de tests de scraping que asuman reuse de `federation_id` por nombre.
