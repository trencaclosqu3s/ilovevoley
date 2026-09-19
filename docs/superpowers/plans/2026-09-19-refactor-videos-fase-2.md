# Refactor de la app `videos` — Fase 2: Extracción a Apps Django Reales

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer los modelos y administradores de los paquetes internos de `videos` a apps Django independientes (`rosters`, `content`, `teams`, `competitions` y `core`), manteniendo el esquema de base de datos intacto mediante `SeparateDatabaseAndState`, actualizando los registros de `django_content_type` para preservar permisos y admin logs, y conservando las vistas, URLs y templates en `videos` sin alterar comportamiento observable ni rutas de acceso existentes.

**Architecture:** Fase 2 aplica el patrón de dos pasos de la spec:
1. **Paso A:** Clavar el nombre de tabla físico (`db_table = 'videos_...'`) en todos los modelos y relaciones M2M existentes en `videos`, generando una migración con `AlterModelTable` cuyo SQL está 100% vacío.
2. **Paso B:** Extraer app por app en orden de menor a mayor acoplamiento (`rosters` → `content` → `teams` → `competitions` → `core`). Cada extracción genera una app Django registrada en `INSTALLED_APPS`, mueve sus modelos conservando su `db_table`, reexporta los nombres desde `videos.models` para retrocompatibilidad total, aplica migraciones espejo `SeparateDatabaseAndState(state_operations=[...], database_operations=[])` con `sqlmigrate` vacío, y actualiza `django_content_type.app_label` vía migración de datos para evitar filas huérfanas o duplicadas.

**Tech Stack:** Django 6.0.8, PostgreSQL 18, Celery 5.6, pytest + pytest-django, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-16-refactor-models-design.md` (Sección 8: Fase 2 — Apps reales).

## Global Constraints

- **Django está fijado en 6.0.8** hasta que `django-celery-beat` soporte 6.1+.
- **Todo comando Django se ejecuta dentro de Docker.** Formato exacto:
  `docker compose -f docker-compose.dev.yml run --rm web <comando>`.
- **`--create-db` es obligatorio en toda ejecución de pytest.**
- **Cero cambios de DDL.** Toda migración generada en esta fase debe producir salida DDL vacía en `python manage.py sqlmigrate <app> <migracion>`. Las tablas físicas (`videos_*`) no se crean, ni se renombran, ni se borran.
- **La app `videos` no se borra.** Conserva su historial de migraciones, vistas, URLs y templates (la mudanza de vistas queda para la Fase 4 según la spec).
- **Compatibilidad total de imports.** Los módulos `videosvoley/videos/models/<dominio>.py` y `videosvoley/videos/models/__init__.py` deben reexportar todos los modelos desde sus nuevas apps para que ningún import existente en el resto del proyecto se rompa.
- **Un commit por tarea**, con número de issue `#68` y marcador `@time <duracion>`.
- Rama de trabajo: `refactor/models-split`.

---

### Task 1: Fijar `db_table` explícito en todos los modelos de `videos` y campos M2M

**Files:**
- Modify: `videosvoley/videos/models/category.py`
- Modify: `videosvoley/videos/models/teams.py`
- Modify: `videosvoley/videos/models/content.py`
- Modify: `videosvoley/videos/models/competitions.py`
- Modify: `videosvoley/videos/models/rosters.py`
- Modify: `videosvoley/videos/models/legacy.py`
- Create: `videosvoley/videos/migrations/0036_set_explicit_db_tables.py`

**Interfaces:**
- Consumes: Los modelos actuales de `videosvoley.videos.models`.
- Produces: `db_table = 'videos_...'` explícito en `Meta` de los 15 modelos y en los dos campos `ManyToManyField` (`League.categories`, `Image.categories`), garantizando que al moverlos a nuevas apps Django no intente cambiar el nombre de tabla física.

- [x] **Step 1: Añadir `db_table` a la clase `Meta` de cada modelo**

En cada uno de los archivos de `videosvoley/videos/models/`:
- `category.py`:
  ```python
  class Category(models.Model):
      class Meta:
          db_table = 'videos_category'
          ...
  ```
- `teams.py`:
  - `Club.Meta.db_table = 'videos_club'`
  - `Team.Meta.db_table = 'videos_team'`
- `content.py`:
  - `Video.Meta.db_table = 'videos_video'`
  - `Comment.Meta.db_table = 'videos_comment'`
  - `Image.Meta.db_table = 'videos_image'`
  - `Image.categories`: añadir `db_table='videos_image_categories'` al `ManyToManyField`
- `competitions.py`:
  - `League.Meta.db_table = 'videos_league'`
  - `League.categories`: añadir `db_table='videos_league_categories'` al `ManyToManyField`
  - `Match.Meta.db_table = 'videos_match'`
  - `ScrapingEndpoint.Meta.db_table = 'videos_scrapingendpoint'`
  - `Standing.Meta.db_table = 'videos_standing'`
- `rosters.py`:
  - `Person.Meta.db_table = 'videos_person'`
  - `PlayerRole.Meta.db_table = 'videos_playerrole'`
  - `StaffRole.Meta.db_table = 'videos_staffrole'`
- `legacy.py`:
  - `Player.Meta.db_table = 'videos_player'`
  - `Staff.Meta.db_table = 'videos_staff'`

- [x] **Step 2: Generar la migración de `db_table`**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations videos -n set_explicit_db_tables`
Expected: Migración `0036_set_explicit_db_tables.py` creada con operaciones `AlterModelTable`.

- [x] **Step 3: Verificar que el SQL generado es 100% vacío**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py sqlmigrate videos 0036`
Expected: Salida sin sentencias DDL (tablas ya tienen esos nombres en BD).

- [x] **Step 4: Aplicar la migración y ejecutar suite de tests**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate videos`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando en verde.

- [x] **Step 5: Commit**

```bash
git add videosvoley/videos/models/ videosvoley/videos/migrations/0036_set_explicit_db_tables.py
git commit -m "refactor(videos): fijar db_table explicito en todos los modelos #68 @time 25m"
```

---

### Task 2: Piloto de extracción: App `rosters`

**Files:**
- Create: `videosvoley/rosters/__init__.py`
- Create: `videosvoley/rosters/apps.py`
- Create: `videosvoley/rosters/models/__init__.py`
- Create: `videosvoley/rosters/models/rosters.py`
- Create: `videosvoley/rosters/models/legacy.py`
- Create: `videosvoley/rosters/admin/__init__.py`
- Create: `videosvoley/rosters/admin/rosters.py`
- Create: `videosvoley/rosters/admin/legacy.py`
- Create: `videosvoley/rosters/migrations/__init__.py`
- Create: `videosvoley/rosters/migrations/0001_initial.py`
- Modify: `config/settings.py` (añadir `'videosvoley.rosters'` a `INSTALLED_APPS`)
- Modify: `videosvoley/videos/models/rosters.py` (reexportar desde `videosvoley.rosters.models`)
- Modify: `videosvoley/videos/models/legacy.py` (reexportar desde `videosvoley.rosters.models`)
- Modify: `videosvoley/videos/admin/rosters.py` (vaciar registro para evitar colisión con `rosters.admin`)
- Modify: `videosvoley/videos/admin/legacy.py` (vaciar registro)
- Create: `videosvoley/videos/migrations/0037_move_rosters_to_app.py`

**Interfaces:**
- Consumes: Modelos de `Person`, `PlayerRole`, `StaffRole`, `Player`, `Staff` de `videosvoley.videos.models`.
- Produces: App `videosvoley.rosters` independiente, reexportada en `videos.models` y `videos.models.rosters`.

- [x] **Step 1: Crear estructura de la app `rosters`**

Crear `videosvoley/rosters/apps.py`:
```python
from django.apps import AppConfig


class RostersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'videosvoley.rosters'
    verbose_name = 'Plantillas'
```
Registrar `'videosvoley.rosters'` en `INSTALLED_APPS` en `config/settings.py`.

- [x] **Step 2: Mover modelos a `videosvoley/rosters/models/`**

Mover el contenido de `videos/models/rosters.py` y `legacy.py` a `videosvoley/rosters/models/`.
`videosvoley/rosters/models/__init__.py`:
```python
from .rosters import Person, PlayerRole, StaffRole, person_photo_upload_path  # noqa: F401
from .legacy import Player, Staff  # noqa: F401

__all__ = ['Person', 'PlayerRole', 'StaffRole', 'Player', 'Staff', 'person_photo_upload_path']
```
En `videosvoley/videos/models/rosters.py`:
```python
"""Reexport de modelos de rosters desde videosvoley.rosters para retrocompatibilidad."""
from videosvoley.rosters.models import Person, PlayerRole, StaffRole, person_photo_upload_path  # noqa: F401

__all__ = ['Person', 'PlayerRole', 'StaffRole', 'person_photo_upload_path']
```
En `videosvoley/videos/models/legacy.py`:
```python
"""Reexport de modelos legacy desde videosvoley.rosters para retrocompatibilidad."""
from videosvoley.rosters.models import Player, Staff  # noqa: F401

__all__ = ['Player', 'Staff']
```

- [x] **Step 3: Mover admin a `videosvoley/rosters/admin/`**

Mover administradores de `PersonAdmin`, `PlayerRoleAdmin`, `StaffRoleAdmin`, `PlayerAdmin`, `StaffAdmin` a `videosvoley/rosters/admin/`.
Vaciar las registraciones de `videosvoley/videos/admin/rosters.py` y `legacy.py` dejando solo comentario explicativo.

- [x] **Step 4: Generar migraciones espejo con `SeparateDatabaseAndState`**

Crear `videosvoley/rosters/migrations/0001_initial.py` con `SeparateDatabaseAndState(state_operations=[...], database_operations=[])` que declare los 5 modelos en `rosters`.
Crear `videosvoley/videos/migrations/0037_move_rosters_to_app.py` con `SeparateDatabaseAndState(state_operations=[...], database_operations=[])` que borre los 5 modelos del estado de `videos`.
Añadir operación `RunPython` para actualizar `django_content_type.app_label`:
```python
def update_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='videos',
        model__in=['person', 'playerrole', 'staffrole', 'player', 'staff']
    ).update(app_label='rosters')

def revert_contenttypes(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    ContentType.objects.filter(
        app_label='rosters',
        model__in=['person', 'playerrole', 'staffrole', 'player', 'staff']
    ).update(app_label='videos')
```

- [x] **Step 5: Verificar `sqlmigrate`, `check` y ejecutar tests**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py sqlmigrate rosters 0001`
Expected: 0 sentencias DDL.
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py sqlmigrate videos 0037`
Expected: 0 sentencias DDL.
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando en verde.

- [x] **Step 6: Commit**

```bash
git add videosvoley/rosters/ config/settings.py videosvoley/videos/
git commit -m "feat(rosters): extraer app rosters con SeparateDatabaseAndState #68 @time 40m"
```

---

### Task 3: Extracción de la App `content`

**Files:**
- Create: `videosvoley/content/__init__.py`
- Create: `videosvoley/content/apps.py`
- Create: `videosvoley/content/models/__init__.py`
- Create: `videosvoley/content/models/content.py`
- Create: `videosvoley/content/admin/__init__.py`
- Create: `videosvoley/content/admin/content.py`
- Create: `videosvoley/content/migrations/__init__.py`
- Create: `videosvoley/content/migrations/0001_initial.py`
- Modify: `config/settings.py` (añadir `'videosvoley.content'` a `INSTALLED_APPS`)
- Modify: `videosvoley/videos/models/content.py` (reexportar desde `videosvoley.content.models`)
- Modify: `videosvoley/videos/admin/content.py` (vaciar registro)
- Create: `videosvoley/videos/migrations/0038_move_content_to_app.py`

**Interfaces:**
- Consumes: Modelos `Video`, `Comment`, `Image` de `videosvoley.videos.models`.
- Produces: App `videosvoley.content` independiente con reexportación en `videos.models`.

- [x] **Step 1: Crear estructura de la app `content` y registrar en `settings.py`**
- [x] **Step 2: Mover modelos `Video`, `Comment`, `Image` a `videosvoley/content/models/`**
- [x] **Step 3: Mover admin a `videosvoley/content/admin/`**
- [x] **Step 4: Generar migraciones espejo `SeparateDatabaseAndState` + actualización de `django_content_type`**
- [x] **Step 5: Verificar `sqlmigrate` (0 DDL), `check`, `makemigrations --check` y tests**
- [x] **Step 6: Commit**

```bash
git add videosvoley/content/ config/settings.py videosvoley/videos/
git commit -m "feat(content): extraer app content con SeparateDatabaseAndState #68 @time 35m"
```

---

### Task 4: Extracción de la App `teams`

**Files:**
- Create: `videosvoley/teams/__init__.py`
- Create: `videosvoley/teams/apps.py`
- Create: `videosvoley/teams/models/__init__.py`
- Create: `videosvoley/teams/models/teams.py`
- Create: `videosvoley/teams/admin/__init__.py`
- Create: `videosvoley/teams/admin/teams.py`
- Create: `videosvoley/teams/migrations/__init__.py`
- Create: `videosvoley/teams/migrations/0001_initial.py`
- Modify: `config/settings.py` (añadir `'videosvoley.teams'` a `INSTALLED_APPS`)
- Modify: `videosvoley/videos/models/teams.py` (reexportar desde `videosvoley.teams.models`)
- Modify: `videosvoley/videos/admin/teams.py` (vaciar registro)
- Create: `videosvoley/videos/migrations/0039_move_teams_to_app.py`

**Interfaces:**
- Consumes: Modelos `Club`, `Team` de `videosvoley.videos.models`.
- Produces: App `videosvoley.teams` independiente con reexportación en `videos.models`.

- [x] **Step 1: Crear estructura de app `teams` y registrar en `settings.py`**
- [x] **Step 2: Mover modelos `Club`, `Team` a `videosvoley/teams/models/`**
- [x] **Step 3: Mover admin a `videosvoley/teams/admin/`**
- [x] **Step 4: Migraciones espejo `SeparateDatabaseAndState` + actualización de `django_content_type`**
- [x] **Step 5: Verificar `sqlmigrate` (0 DDL), `check`, `makemigrations --check` y tests**
- [x] **Step 6: Commit**

```bash
git add videosvoley/teams/ config/settings.py videosvoley/videos/
git commit -m "feat(teams): extraer app teams con SeparateDatabaseAndState #68 @time 35m"
```

---

### Task 5: Extracción de la App `competitions`

**Files:**
- Create: `videosvoley/competitions/__init__.py`
- Create: `videosvoley/competitions/apps.py`
- Create: `videosvoley/competitions/models/__init__.py`
- Create: `videosvoley/competitions/models/competitions.py`
- Create: `videosvoley/competitions/admin/__init__.py`
- Create: `videosvoley/competitions/admin/competitions.py`
- Create: `videosvoley/competitions/migrations/__init__.py`
- Create: `videosvoley/competitions/migrations/0001_initial.py`
- Modify: `config/settings.py` (añadir `'videosvoley.competitions'` a `INSTALLED_APPS`)
- Modify: `videosvoley/videos/models/competitions.py` (reexportar desde `videosvoley.competitions.models`)
- Modify: `videosvoley/videos/admin/competitions.py` (vaciar registro)
- Create: `videosvoley/videos/migrations/0040_move_competitions_to_app.py`

**Interfaces:**
- Consumes: Modelos `League`, `Match`, `Standing`, `ScrapingEndpoint` de `videosvoley.videos.models`.
- Produces: App `videosvoley.competitions` independiente con reexportación en `videos.models`.

- [ ] **Step 1: Crear estructura de app `competitions` y registrar en `settings.py`**
- [ ] **Step 2: Mover modelos a `videosvoley/competitions/models/`**
- [ ] **Step 3: Mover admin a `videosvoley/competitions/admin/`**
- [ ] **Step 4: Migraciones espejo `SeparateDatabaseAndState` + actualización de `django_content_type`**
- [ ] **Step 5: Verificar `sqlmigrate` (0 DDL), `check`, `makemigrations --check` y tests**
- [ ] **Step 6: Commit**

```bash
git add videosvoley/competitions/ config/settings.py videosvoley/videos/
git commit -m "feat(competitions): extraer app competitions con SeparateDatabaseAndState #68 @time 40m"
```

---

### Task 6: Mover `Category` a `videosvoley.core`

**Files:**
- Create: `videosvoley/core/models/category.py`
- Modify: `videosvoley/core/models/__init__.py` (o `videosvoley/core/models.py`)
- Modify: `videosvoley/core/admin.py` (registrar `CategoryAdmin`)
- Modify: `videosvoley/videos/models/category.py` (reexportar desde `videosvoley.core.models`)
- Modify: `videosvoley/videos/admin/category.py` (vaciar registro)
- Create: `videosvoley/core/migrations/0002_move_category_to_core.py`
- Create: `videosvoley/videos/migrations/0041_move_category_to_core.py`

**Interfaces:**
- Consumes: Modelo `Category` de `videosvoley.videos.models`.
- Produces: `Category` en `videosvoley.core.models`, disponible para todas las apps y reexportado en `videos.models`.

- [ ] **Step 1: Mover modelo `Category` a `videosvoley/core/models/`**
- [ ] **Step 2: Mover `CategoryAdmin` a `videosvoley/core/admin.py` y vaciar en `videos`**
- [ ] **Step 3: Reexportar `Category` en `videosvoley/videos/models/category.py`**
- [ ] **Step 4: Migraciones espejo `SeparateDatabaseAndState` + actualización de `django_content_type`**
- [ ] **Step 5: Verificar `sqlmigrate` (0 DDL), `check`, `makemigrations --check` y tests**
- [ ] **Step 6: Commit**

```bash
git add videosvoley/core/ videosvoley/videos/
git commit -m "feat(core): mover Category a videosvoley.core #68 @time 30m"
```

---

### Task 7: Verificación final de Fase 2

**Interfaces:**
- Consumes: Todas las apps y modelos migrados en las tareas 1-6.
- Produces: Certificación de integridad de base de datos, URLs y suite de tests.

- [ ] **Step 1: Verificar que ningún comando o vista tiene dependencias rotas**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Expected: 0 issues.

- [ ] **Step 2: Verificar que no hay migraciones pendientes ni DDL generado**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 3: Verificar recuento de filas en cada tabla física**

Comprobar que todas las tablas `videos_*` mantienen exactamente el mismo recuento de filas antes y después.

- [ ] **Step 4: Ejecutar suite completa con `--create-db`**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando en verde.

- [ ] **Step 5: Commit de documentación y checklist**

```bash
git add docs/superpowers/plans/2026-09-19-refactor-videos-fase-2.md
git commit -m "docs: completar checklist de verificacion de fase 2 #68 @time 10m"
```
