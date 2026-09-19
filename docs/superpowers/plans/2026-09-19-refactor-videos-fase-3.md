# Refactor videosvoley — Fase 3: Retirada de deuda técnica

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconciliar y retirar los modelos obsoletos `Player` y `Staff` en favor de `Person`/`PlayerRole`/`StaffRole`, migrar y eliminar el campo deprecado `League.category` en favor de `categories` M2M, y limpiar el residuo `core/tasks/`.

**Architecture:** 
1. Migración de datos idempotente en `rosters` que asegura que cualquier `Player` o `Staff` remanente quede transferido a `Person`, `PlayerRole` y `StaffRole`.
2. Eliminación de los modelos `Player` y `Staff` mediante migración `DeleteModel` en `rosters`, eliminando su código y admin pero preservando las funciones stub `player_photo_upload_path` y `staff_photo_upload_path` en `videos.models` para no romper la reproducción histórica de la migración `videos.0019` con `--create-db`.
3. Migración de datos en `competitions` para consolidar `category` en `categories`, limpieza de referencias en `calendar_feed.py`, y `RemoveField` de `League.category`.
4. Eliminación de `videosvoley/core/tasks/`.

**Tech Stack:** Django 6.0.8, PostgreSQL, pytest, Docker Compose.

**Spec:** [`docs/superpowers/specs/2026-09-16-refactor-models-design.md`](file:///Users/jamartinmari/orca/workspaces/videosvoley/refactor-de-la-app-monol-tica-videos-paquetes-y/docs/superpowers/specs/2026-09-16-refactor-models-design.md) (Sección 9: Fase 3 — Retirada de deuda).

## Global Constraints

- Django está fijado en 6.0.8.
- Todo comando Django se ejecuta dentro de Docker: `docker compose -f docker-compose.dev.yml run --rm web <comando>`.
- `--create-db` es obligatorio en toda ejecución de pytest: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`.
- Preservar compatibilidad con migraciones históricas: `player_photo_upload_path` y `staff_photo_upload_path` deben seguir existiendo en `videosvoley.videos.models` como stubs porque `videos.0019_player_staff.py` las referencia.
- Cero pérdida de datos: la migración de datos debe ser idempotente y verificar duplicados por identidad antes de crear registros nuevos.

---

### Task 1: Migración de datos: Reconciliar `Player` y `Staff` con `Person` y Roles

**Files:**
- Create: `videosvoley/rosters/migrations/0003_reconcile_legacy_players_staff.py`

**Interfaces:**
- Consumes: Modelos `Player`, `Staff`, `Person`, `PlayerRole`, `StaffRole` desde la app `rosters`.
- Produces: Datos reconciliados en base de datos; todo `Player` tiene su `Person` y `PlayerRole`; todo `Staff` tiene su `Person` y `StaffRole`.

- [x] **Step 1: Crear migración de datos de reconciliación**

Crear `videosvoley/rosters/migrations/0003_reconcile_legacy_players_staff.py`:

```python
from django.db import migrations


def reconcile_players_and_staff(apps, schema_editor):
    Person = apps.get_model('rosters', 'Person')
    PlayerRole = apps.get_model('rosters', 'PlayerRole')
    StaffRole = apps.get_model('rosters', 'StaffRole')
    Player = apps.get_model('rosters', 'Player')
    Staff = apps.get_model('rosters', 'Staff')

    # Reconciliar Players
    for player in Player.objects.all():
        first_name = (player.first_name or '').strip()
        last_name = (player.last_name or '').strip()
        
        # Buscar Person por identidad única o por nombre y apellidos
        person = None
        if player.birth_date:
            person = Person.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
                birth_date=player.birth_date,
            ).first()
        if not person:
            person = Person.objects.filter(
                first_name__iexact=first_name,
                last_name__iexact=last_name,
            ).first()

        if not person:
            person = Person.objects.create(
                first_name=first_name,
                last_name=last_name,
                birth_date=player.birth_date,
                photo=player.photo,
                user=player.user,
                notes=player.notes or '',
                is_active=player.is_active,
                created_at=player.created_at,
            )

        # Crear PlayerRole si no existe para ese equipo
        if not PlayerRole.objects.filter(person=person, team=player.team).exists():
            PlayerRole.objects.create(
                person=person,
                team=player.team,
                jersey_number=player.jersey_number,
                position=player.position,
                is_active=player.is_active,
                notes=player.notes or '',
                created_at=player.created_at,
            )

    # Reconciliar Staff
    for staff in Staff.objects.all():
        first_name = (staff.first_name or '').strip()
        last_name = (staff.last_name or '').strip()

        person = Person.objects.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name,
        ).first()

        if not person:
            person = Person.objects.create(
                first_name=first_name,
                last_name=last_name,
                birth_date=None,
                photo=staff.photo,
                email=staff.email or '',
                phone=staff.phone or '',
                user=staff.user,
                notes=staff.notes or '',
                is_active=staff.is_active,
                created_at=staff.created_at,
            )
        else:
            updated = False
            if not person.email and staff.email:
                person.email = staff.email
                updated = True
            if not person.phone and staff.phone:
                person.phone = staff.phone
                updated = True
            if not person.photo and staff.photo:
                person.photo = staff.photo
                updated = True
            if updated:
                person.save()

        # Crear StaffRole si no existe
        if not StaffRole.objects.filter(person=person, team=staff.team, role=staff.role).exists():
            StaffRole.objects.create(
                person=person,
                team=staff.team,
                role=staff.role,
                is_active=staff.is_active,
                notes=staff.notes or '',
                created_at=staff.created_at,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rosters', '0002_alter_player_team_alter_playerrole_team_and_more'),
    ]

    operations = [
        migrations.RunPython(reconcile_players_and_staff, noop_reverse),
    ]
```

- [x] **Step 2: Aplicar migración y verificar**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate rosters`
Expected: `Applying rosters.0003_reconcile_legacy_players_staff... OK`.

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando.

- [x] **Step 3: Commit**

```bash
git add videosvoley/rosters/migrations/0003_reconcile_legacy_players_staff.py
git commit -m "feat(rosters): migrar datos residuales de Player y Staff a Person-Role #68 @time 25m"
```

---

### Task 2: Retirar modelos `Player` y `Staff`, admin inlines y limpiar `legacy.py`

**Files:**
- Create: `videosvoley/rosters/migrations/0004_delete_legacy_player_staff.py`
- Modify: `videosvoley/rosters/models/legacy.py` (eliminar clases `Player` y `Staff`)
- Modify: `videosvoley/rosters/models/__init__.py` (remover `Player` y `Staff` de exports)
- Modify: `videosvoley/rosters/admin/legacy.py` (eliminar `PlayerAdmin`, `StaffAdmin`, `PlayerInline`, `StaffInline`)
- Modify: `videosvoley/videos/models/legacy.py` (mantener stubs de upload paths para migraciones históricas, retirar `Player` y `Staff`)
- Modify: `videosvoley/videos/models/__init__.py` (remover `Player` y `Staff`)

**Interfaces:**
- Consumes: `rosters.migrations.0003_reconcile_legacy_players_staff`.
- Produces: Eliminación de modelos `Player` y `Staff` en el schema de Django y tablas `videos_player`, `videos_staff`.

- [ ] **Step 1: Crear migración para eliminar `Player` y `Staff`**

Ejecutar `makemigrations rosters` o crear `videosvoley/rosters/migrations/0004_delete_legacy_player_staff.py`:

```python
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rosters', '0003_reconcile_legacy_players_staff'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Player',
        ),
        migrations.DeleteModel(
            name='Staff',
        ),
    ]
```

- [ ] **Step 2: Limpiar modelos y admin en `rosters`**

En `videosvoley/rosters/models/legacy.py`:
Dejar solo upload paths de compatibilidad si aplica o vaciar el archivo.
En `videosvoley/rosters/models/__init__.py`:
Remover imports de `Player` y `Staff`.
En `videosvoley/rosters/admin/legacy.py`:
Vaciar contenido (o dejar docstring explicativo).

- [ ] **Step 3: Limpiar re-exports en `videos.models` preservando upload stubs**

En `videosvoley/videos/models/legacy.py`:
Mantener:
```python
"""Upload paths de compatibilidad para migraciones históricas de videos."""


def player_photo_upload_path(instance, filename):
    return f'players/{filename}'


def staff_photo_upload_path(instance, filename):
    return f'staff/{filename}'


__all__ = ['player_photo_upload_path', 'staff_photo_upload_path']
```
En `videosvoley/videos/models/__init__.py`:
Remover `Player` y `Staff` de imports y `__all__`. Mantener `player_photo_upload_path` y `staff_photo_upload_path`.

- [ ] **Step 4: Aplicar migración y verificar**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate`
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Expected: 0 issues.
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Expected: No changes detected.
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando.

- [ ] **Step 5: Commit**

```bash
git add videosvoley/rosters/ videosvoley/videos/models/
git commit -m "refactor(rosters): eliminar modelos legados Player y Staff #68 @time 30m"
```

---

### Task 3: Migrar y eliminar campo `League.category` en `competitions`

**Files:**
- Create: `videosvoley/competitions/migrations/0003_migrate_league_category_data.py`
- Create: `videosvoley/competitions/migrations/0004_remove_league_category.py`
- Modify: `videosvoley/competitions/models/competitions.py` (remover campo `category` de `League`)
- Modify: `videosvoley/videos/calendar_feed.py` (limpiar referencias a `league.category`)

**Interfaces:**
- Consumes: `competitions.models.League.category`.
- Produces: Todas las categorías consolidadas en `League.categories` M2M; eliminación de la columna física `category_id` en `videos_league`.

- [ ] **Step 1: Migración de datos para consolidar `category` en `categories`**

Crear `videosvoley/competitions/migrations/0003_migrate_league_category_data.py`:

```python
from django.db import migrations


def migrate_category_to_categories(apps, schema_editor):
    League = apps.get_model('competitions', 'League')
    for league in League.objects.filter(category__isnull=False):
        league.categories.add(league.category)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('competitions', '0002_alter_league_categories_alter_league_category'),
    ]

    operations = [
        migrations.RunPython(migrate_category_to_categories, noop_reverse),
    ]
```

- [ ] **Step 2: Actualizar `videosvoley/videos/calendar_feed.py`**

Eliminar referencias al campo obsoleto `league.category`:
- En `items()`: simplificar `Q(league__categories__in=categories) | Q(is_friendly=True)`.
- En `item_title()` y `item_description()`: no buscar fallback a `item.league.category`.

- [ ] **Step 3: Remover campo `category` de `League` y generar migración**

En `videosvoley/competitions/models/competitions.py`:
Eliminar el campo `category = models.ForeignKey(...)` de `League`.

Generar migración:
`docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations competitions -n remove_league_category`
(o crear `videosvoley/competitions/migrations/0004_remove_league_category.py` con `migrations.RemoveField(model_name='league', name='category')`).

- [ ] **Step 4: Aplicar migraciones y verificar**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate competitions`
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Expected: 0 issues.
Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Expected: No changes detected.
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando.

- [ ] **Step 5: Commit**

```bash
git add videosvoley/competitions/ videosvoley/videos/calendar_feed.py
git commit -m "feat(competitions): migrar y eliminar campo obsoleto League.category #68 @time 25m"
```

---

### Task 4: Eliminar directorio residuo `videosvoley/core/tasks/`

**Files:**
- Delete: `videosvoley/core/tasks/__init__.py`
- Delete: `videosvoley/core/tasks/` directory

**Interfaces:**
- Consumes: Directorio residual sin uso.
- Produces: Limpieza del árbol de directorios de `videosvoley.core`.

- [ ] **Step 1: Eliminar el directorio `videosvoley/core/tasks/`**

Run: `rm -rf videosvoley/core/tasks/`

- [ ] **Step 2: Verificar tests**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando.

- [ ] **Step 3: Commit**

```bash
git add videosvoley/core/tasks/
git commit -m "refactor(core): eliminar paquete residual core/tasks #68 @time 5m"
```

---

### Task 5: Verificación final de la Fase 3

**Interfaces:**
- Consumes: Todo el trabajo completado en las tareas 1-4.
- Produces: Certificación de integridad de base de datos, código y tests.

- [ ] **Step 1: Ejecutar check del sistema**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Expected: 0 issues.

- [ ] **Step 2: Verificar que no hay migraciones pendientes**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 3: Ejecutar suite completa con `--create-db`**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 98 tests pasando en verde.

- [ ] **Step 4: Commit de documentación y checklist**

```bash
git add docs/superpowers/plans/2026-09-19-refactor-videos-fase-3.md
git commit -m "docs: completar checklist de verificacion de fase 3 #68 @time 10m"
```
