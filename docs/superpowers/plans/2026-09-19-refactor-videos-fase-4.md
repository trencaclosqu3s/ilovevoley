# Refactor de la App Videos: Fase 4 — Mudanza de vistas, URLs y templates

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer vistas, formularios, URLs y templates de la app monolítica `videos` a sus respectivas apps de dominio (`rosters`, `content`, `teams`, `competitions` y `core`), renombrando los namespaces de `videos:*` a `<app>:*` de forma segura mediante un test de barrido estático exhaustivo.

**Architecture:** Se sigue la estrategia en dos pasos descrita en la sección 10 del diseño técnico: Paso 4a (mover código de vistas y forms con re-export en `videos` para preservar compatibilidad) y Paso 4b (extraer URLconfs con su `app_name`, incluir en `config/urls.py`, trasladar templates a `<app>/templates/<app>/` y renombrar referencias `videos:x` a `<app>:x`). La seguridad en runtime se garantiza mediante un test de barrido estático previo (`test_url_reverse_sweep.py`) que comprueba que todas las referencias `{% url %}` y `reverse()` se resuelven antes y después de cada cambio.

**Tech Stack:** Django 6.0.8, pytest-django, Docker, Python 3.13.

**Spec:** [`docs/superpowers/specs/2026-09-16-refactor-models-design.md`](file:///Users/jamartinmari/orca/workspaces/videosvoley/refactor-de-la-app-monol-tica-videos-paquetes-y/docs/superpowers/specs/2026-09-16-refactor-models-design.md) (Sección 10: Fase 4 — Mudanza de vistas, URLs y templates).

## Global Constraints

- Django está fijado en 6.0.8.
- Todo comando Django se ejecuta dentro de Docker: `docker compose -f docker-compose.dev.yml run --rm web <comando>`.
- `--create-db` es obligatorio en toda ejecución completa de pytest.
- Todo commit debe incluir `#68` y `@time <duracion>` (ej. `#68 @time 25m`).
- Nunca hacer `git push` de forma automática.
- Código en inglés; commits, documentación y comunicación en español.
- Cero regressions: el test de barrido estático debe estar en verde antes y después de cada commit.
- Al terminar la Fase 4, el directorio `videosvoley/templates/videos/` debe quedar vacío y eliminarse, y no debe quedar ninguna referencia a `videos:` en templates ni en Python.

---

### Task 0: Red de seguridad — Test de barrido estático de URLs y corrección previa

**Files:**
- Create: `videosvoley/core/tests/test_url_reverse_sweep.py`
- Modify: `videosvoley/videos/views/content.py:195` (corregir `redirect('video_detail', ...)` a `redirect('videos:video_detail', ...)`)

**Interfaces:**
- Consumes: Django URL resolver, templates en `videosvoley/templates/` y código Python en `videosvoley/`.
- Produces: Test automatizado de regresión que analiza estáticamente cada `{% url %}` y `reverse()` / `redirect()`.

- [x] **Step 1: Corregir llamada no cualificada en `videosvoley/videos/views/content.py`**

Modificar la línea 195:
```python
            return redirect('videos:video_detail', video_id=video.id)
```

- [x] **Step 2: Crear el test de barrido estático `test_url_reverse_sweep.py`**

Crear `videosvoley/core/tests/test_url_reverse_sweep.py`:
```python
import re
from pathlib import Path
import pytest
from django.conf import settings
from django.urls import get_resolver


def _can_resolve(url_name: str) -> bool:
    """Comprueba si un nombre de URL o URL con namespace puede resolverse en el URLconf actual."""
    resolver = get_resolver()
    if ':' in url_name:
        parts = url_name.split(':')
        cur = resolver
        for part in parts[:-1]:
            if part not in cur.namespace_dict:
                return False
            cur = cur.namespace_dict[part][1]
        return parts[-1] in cur.reverse_dict
    return url_name in resolver.reverse_dict


def test_template_url_tags_can_resolve():
    """Barre todos los templates HTML y comprueba que cada {% url '...' %} se puede resolver."""
    url_re = re.compile(r'{%\s*url\s+[\'\"]([^\'\"]+)[\'\"]')
    base_dir = Path(settings.BASE_DIR) / 'videosvoley'
    
    template_files = list(base_dir.glob('templates/**/*.html'))
    # También incluir templates dentro de cada app cuando se muden
    template_files.extend(base_dir.glob('*/templates/**/*.html'))
    
    failures = []
    checked = 0
    
    for template_path in template_files:
        content = template_path.read_text(encoding='utf-8')
        for match in url_re.finditer(content):
            url_name = match.group(1)
            checked += 1
            if not _can_resolve(url_name):
                failures.append(f"{template_path.relative_to(base_dir)}: '{url_name}' cannot be resolved")
                
    assert checked > 100, f"Se esperaban más de 100 referencias url en templates, se encontraron {checked}"
    assert not failures, f"Fallo al resolver URLs en templates:\n" + "\n".join(failures)


def test_python_reverse_calls_can_resolve():
    """Barre todo el código Python y comprueba que las llamadas reverse(...) y redirect(...) literales se resuelven."""
    rev_re = re.compile(r'(?:reverse|redirect)\s*\(\s*[\'\"]([^\'\"]+)[\'\"]')
    base_dir = Path(settings.BASE_DIR) / 'videosvoley'
    
    py_files = [
        p for p in base_dir.glob('**/*.py')
        if 'migrations' not in str(p) and 'tests' not in str(p)
    ]
    
    failures = []
    checked = 0
    
    for py_path in py_files:
        content = py_path.read_text(encoding='utf-8')
        for match in rev_re.finditer(content):
            url_name = match.group(1)
            # Ignorar redirects a rutas absolutas ej. '/videos/'
            if url_name.startswith('/'):
                continue
            checked += 1
            if not _can_resolve(url_name):
                failures.append(f"{py_path.relative_to(base_dir)}: '{url_name}' cannot be resolved")
                
    assert checked >= 15, f"Se esperaban al menos 15 referencias literales a reverse/redirect, se encontraron {checked}"
    assert not failures, f"Fallo al resolver URLs en Python:\n" + "\n".join(failures)
```

- [x] **Step 3: Ejecutar el test de barrido y verificar que pasa en verde**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/core/tests/test_url_reverse_sweep.py -v --tb=short`
Expected: 2 passed.

- [x] **Step 4: Commit**

```bash
git add videosvoley/videos/views/content.py videosvoley/core/tests/test_url_reverse_sweep.py
git commit -m "test(core): anadir test de barrido estatico de URLs y corregir redirect en video_detail #68 @time 20m"
```

---

### Task 1: Mudanza de vistas, URLs y templates de `rosters`

**Files:**
- Create: `videosvoley/rosters/views.py`
- Create: `videosvoley/rosters/forms.py`
- Create: `videosvoley/rosters/urls.py`
- Move: `videosvoley/templates/videos/person_*.html`, `role_form.html`, `roster_overview.html` a `videosvoley/rosters/templates/rosters/`
- Modify: `videosvoley/videos/views/rosters.py` (re-exportar desde `videosvoley.rosters.views`)
- Modify: `videosvoley/videos/forms/rosters.py` (re-exportar desde `videosvoley.rosters.forms`)
- Modify: `videosvoley/videos/forms/__init__.py`
- Modify: `config/urls.py` (incluir `rosters.urls` con `app_name='rosters'`)
- Modify: `videosvoley/videos/urls.py` (mantener delegación para compatibilidad temporal)
- Modify: Templates y vistas actualizando `videos:person_*`, `videos:player_role_*`, `videos:staff_role_*`, `videos:roster_overview` a `rosters:*`

**Interfaces:**
- Consumes: Modelos `Person`, `PlayerRole`, `StaffRole`, `Team`, `Category`.
- Produces: URLs bajo namespace `rosters:` y templates en `rosters/`.

- [x] **Step 1: Crear `videosvoley/rosters/forms.py` y re-exportar en `videos/forms/rosters.py`**
...
- [x] **Step 2: Crear `videosvoley/rosters/views.py` y re-exportar en `videos/views/rosters.py`**
...
- [x] **Step 3: Crear `videosvoley/rosters/urls.py` y añadir a `config/urls.py`**
...
- [x] **Step 4: Mover templates a `videosvoley/rosters/templates/rosters/` y actualizar referencias**
...
- [x] **Step 5: Ejecutar test de barrido y suite de tests**
...
- [x] **Step 6: Commit**

```bash
git add videosvoley/rosters/ videosvoley/videos/ config/urls.py videosvoley/templates/
git commit -m "feat(rosters): mudar vistas, formularios, urls y templates de rosters #68 @time 35m"
```

---

### Task 2: Mudanza de vistas, URLs y templates de `content`

**Files:**
- Create: `videosvoley/content/views.py` (o paquete `content/views/`)
- Create: `videosvoley/content/forms.py`
- Create: `videosvoley/content/urls.py`
- Move: `videosvoley/templates/videos/video_*.html`, `image_*.html`, `album_group_images.html`, `match_images.html` a `videosvoley/content/templates/content/`
- Modify: `videosvoley/videos/views/content.py` (re-exportar desde `videosvoley.content.views`)
- Modify: `videosvoley/videos/forms/content.py` (re-exportar desde `videosvoley.content.forms`)
- Modify: `config/urls.py` (incluir `content.urls` con `app_name='content'`)
- Modify: `videosvoley/videos/urls.py`
- Modify: Templates y vistas actualizando `videos:video_*`, `videos:image_*`, `videos:album_group_images`, `videos:match_images` a `content:*`

**Interfaces:**
- Consumes: Modelos `Video`, `Image`, `Comment`.
- Produces: URLs bajo namespace `content:` y templates en `content/`.

- [x] **Step 1: Crear `videosvoley/content/forms.py` y re-exportar en `videos/forms/content.py`**

Mover contenido de `videosvoley/videos/forms/content.py` a `videosvoley/content/forms.py`.
Re-exportar en `videosvoley/videos/forms/content.py`.

- [x] **Step 2: Crear vistas de content en `videosvoley/content/views.py` y re-exportar**

Mover lógica de `videosvoley/videos/views/content.py` y vistas de moderación de imágenes de `videosvoley/videos/views/moderation.py` (`image_moderation`, `image_moderate_action`, `image_moderate_bulk`, `moderate_image_api`) a `videosvoley/content/views.py`.
Actualizar los nombres de template renderizados a `'content/...'`:
- `'videos/video_list.html'` -> `'content/video_list.html'`
- `'videos/video_detail.html'` -> `'content/video_detail.html'`
- `'videos/video_form.html'` -> `'content/video_form.html'`
- `'videos/video_bulk_form.html'` -> `'content/video_bulk_form.html'`
- `'videos/image_gallery.html'` -> `'content/image_gallery.html'`
- `'videos/image_detail.html'` -> `'content/image_detail.html'`
- `'videos/image_upload.html'` -> `'content/image_upload.html'`
- `'videos/image_bulk_upload.html'` -> `'content/image_bulk_upload.html'`
- `'videos/album_group_images.html'` -> `'content/album_group_images.html'`
- `'videos/match_images.html'` -> `'content/match_images.html'`
- `'videos/image_moderation.html'` -> `'content/image_moderation.html'`
- `'videos/image_moderate.html'` -> `'content/image_moderate.html'`
Actualizar redirects en `content/views.py` a `content:*`.
Re-exportar todo en `videosvoley/videos/views/content.py`.

- [x] **Step 3: Crear `videosvoley/content/urls.py` y registrar en `config/urls.py`**

Crear `videosvoley/content/urls.py` con `app_name = 'content'`:
```python
from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    # URLs de videos
    path('', views.video_list, name='video_list'),
    path('nuevo/', views.video_create, name='video_create'),
    path('nuevo-multiple/', views.video_bulk_create, name='video_bulk_create'),
    path('<int:video_id>/', views.video_detail, name='video_detail'),
    
    # URLs de imágenes
    path('imagenes/', views.image_gallery_albums, name='image_gallery'),
    path('imagenes/individual/', views.image_gallery, name='image_gallery_individual'),
    path('imagenes/subir/', views.image_upload, name='image_upload'),
    path('imagenes/subir-multiples/', views.image_bulk_upload, name='image_bulk_upload'),
    path('imagenes/<int:image_id>/', views.image_detail, name='image_detail'),
    path('partidos/<int:match_id>/imagenes/', views.match_images, name='match_images'),
    path('imagenes/album/<uuid:album_group_id>/', views.album_group_images, name='album_group_images'),
    
    # URLs de moderación de imágenes
    path('admin/imagenes/moderar/', views.image_moderation, name='image_moderation'),
    path('admin/imagenes/<int:image_id>/moderar/', views.image_moderate_action, name='image_moderate_action'),
    path('admin/imagenes/moderar-masivo/', views.image_moderate_bulk, name='image_moderate_bulk'),
    path('api/images/<int:image_id>/moderate/', views.moderate_image_api, name='moderate_image_api'),
]
```
En `config/urls.py`:
```python
    path('content/', include('videosvoley.content.urls', namespace='content')),
```

- [x] **Step 4: Mover templates a `videosvoley/content/templates/content/` y actualizar referencias**

Mover los templates de videos e imágenes.
Actualizar referencias en templates (`navbar.html`, `base.html`, `400.html`, etc.) y Python (`core/views.py:landing`, etc.):
- `videos:video_*` -> `content:video_*`
- `videos:image_*` -> `content:image_*`
- `videos:album_group_images` -> `content:album_group_images`
- `videos:match_images` -> `content:match_images`

- [x] **Step 5: Ejecutar test de barrido y suite de tests**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/core/tests/test_url_reverse_sweep.py -v --tb=short`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: todos los tests pasando en verde.

- [x] **Step 6: Commit**

```bash
git add videosvoley/content/ videosvoley/videos/ config/urls.py videosvoley/templates/
git commit -m "feat(content): mudar vistas, formularios, urls y templates de content #68 @time 40m"
```

---

### Task 3: Mudanza de vistas, URLs y templates de `teams`

**Files:**
- Create: `videosvoley/teams/views.py`
- Create: `videosvoley/teams/urls.py`
- Move: `videosvoley/templates/videos/team_list.html`, `team_roster.html` a `videosvoley/teams/templates/teams/`
- Modify: `videosvoley/videos/views/teams.py` (re-exportar desde `videosvoley.teams.views`)
- Modify: `config/urls.py` (incluir `teams.urls` con `app_name='teams'`)
- Modify: `videosvoley/videos/urls.py`
- Modify: Templates y vistas actualizando `videos:team_list`, `videos:team_roster`, `videos:ajax_register_team` a `teams:*`

**Interfaces:**
- Consumes: Modelos `Club`, `Team`, `PlayerRole`, `StaffRole`, `Category`.
- Produces: URLs bajo namespace `teams:` y templates en `teams/`.

- [x] **Step 1: Crear `videosvoley/teams/views.py` y re-exportar en `videos/views/teams.py`**

Mover lógica de `videosvoley/videos/views/teams.py` a `videosvoley/teams/views.py`.
Actualizar nombres de templates renderizados:
- `'videos/team_list.html'` -> `'teams/team_list.html'`
- `'videos/team_roster.html'` -> `'teams/team_roster.html'`
Actualizar redirects en `teams/views.py` a `teams:*` (ej. `teams:team_list`).
En `videosvoley/videos/views/teams.py`, re-exportar:
```python
from videosvoley.teams.views import *  # noqa: F401,F403
from videosvoley.teams.views import ajax_register_team, team_list, team_roster

__all__ = ['ajax_register_team', 'team_list', 'team_roster']
```

- [x] **Step 2: Crear `videosvoley/teams/urls.py` y registrar en `config/urls.py`**

Crear `videosvoley/teams/urls.py` con `app_name = 'teams'`:
```python
from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    path('equipos/', views.team_list, name='team_list'),
    path('equipos/<int:team_id>/plantilla/', views.team_roster, name='team_roster'),
    path('ajax/register-team/', views.ajax_register_team, name='ajax_register_team'),
]
```
En `config/urls.py`:
```python
    path('teams/', include('videosvoley.teams.urls', namespace='teams')),
```

- [x] **Step 3: Mover templates a `videosvoley/teams/templates/teams/` y actualizar referencias**

Mover:
- `videosvoley/templates/videos/team_list.html` -> `videosvoley/teams/templates/teams/team_list.html`
- `videosvoley/templates/videos/team_roster.html` -> `videosvoley/teams/templates/teams/team_roster.html`
Actualizar en templates y código Python:
- `videos:team_list` -> `teams:team_list`
- `videos:team_roster` -> `teams:team_roster`
- `videos:ajax_register_team` -> `teams:ajax_register_team`

- [x] **Step 4: Ejecutar test de barrido y suite de tests**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/core/tests/test_url_reverse_sweep.py -v --tb=short`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: todos los tests pasando en verde.

- [x] **Step 5: Commit**

```bash
git add videosvoley/teams/ videosvoley/videos/ config/urls.py videosvoley/templates/
git commit -m "feat(teams): mudar vistas, urls y templates de teams #68 @time 25m"
```

---

### Task 4: Mudanza de vistas, URLs y templates de `competitions`

**Files:**
- Create: `videosvoley/competitions/views.py`
- Create: `videosvoley/competitions/forms.py`
- Create: `videosvoley/competitions/urls.py`
- Create: `videosvoley/competitions/calendar_feed.py`
- Move: `videosvoley/templates/videos/league_*.html`, `match_detail.html`, `calendar.html`, `standings.html`, `friendly_match_form.html` a `videosvoley/competitions/templates/competitions/`
- Modify: `videosvoley/videos/views/competitions.py` (re-exportar desde `videosvoley.competitions.views`)
- Modify: `videosvoley/videos/forms/competitions.py` (re-exportar desde `videosvoley.competitions.forms`)
- Modify: `videosvoley/videos/calendar_feed.py` (re-exportar desde `videosvoley.competitions.calendar_feed`)
- Modify: `config/urls.py` (incluir `competitions.urls` con `app_name='competitions'`)
- Modify: `videosvoley/videos/urls.py`
- Modify: Templates y vistas actualizando `videos:league_*`, `videos:match_detail`, `videos:calendar_*`, `videos:standings_*`, `videos:friendly_*`, `videos:ajax_*` a `competitions:*`

**Interfaces:**
- Consumes: Modelos `League`, `Match`, `Standing`, `Team`, `Category`.
- Produces: URLs bajo namespace `competitions:` y templates en `competitions/`.

- [ ] **Step 1: Crear `videosvoley/competitions/forms.py` y `calendar_feed.py` con re-exports**

Mover `videosvoley/videos/forms/competitions.py` a `videosvoley/competitions/forms.py` y re-exportar en `videos/forms/competitions.py`.
Mover `videosvoley/videos/calendar_feed.py` a `videosvoley/competitions/calendar_feed.py` y re-exportar en `videos/calendar_feed.py`.

- [ ] **Step 2: Crear `videosvoley/competitions/views.py` y re-exportar en `videos/views/competitions.py`**

Mover lógica de `videosvoley/videos/views/competitions.py` a `videosvoley/competitions/views.py`.
Actualizar nombres de templates renderizados:
- `'videos/league_list.html'` -> `'competitions/league_list.html'`
- `'videos/league_detail.html'` -> `'competitions/league_detail.html'`
- `'videos/match_detail.html'` -> `'competitions/match_detail.html'`
- `'videos/calendar.html'` -> `'competitions/calendar.html'`
- `'videos/standings.html'` -> `'competitions/standings.html'`
- `'videos/friendly_match_form.html'` -> `'competitions/friendly_match_form.html'`
Actualizar redirects en `competitions/views.py` a `competitions:*`.
Re-exportar todo en `videosvoley/videos/views/competitions.py`.

- [ ] **Step 3: Crear `videosvoley/competitions/urls.py` y registrar en `config/urls.py`**

Crear `videosvoley/competitions/urls.py` con `app_name = 'competitions'`:
```python
from django.urls import path
from . import views
from .calendar_feed import UserMatchesFeed

app_name = 'competitions'

urlpatterns = [
    # URLs de ligas y partidos
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    path('partidos/<int:match_id>/', views.match_detail, name='match_detail'),
    path('calendario/', views.calendar_view, name='calendar_view'),
    path('clasificacion/', views.standings_view, name='standings_view'),
    path('calendario/amistoso/nuevo/', views.friendly_match_create, name='friendly_match_create'),
    
    # Calendar subscription feed (ICS)
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),
    
    # URLs AJAX
    path('ajax/matches-by-category/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/teams-by-league-category/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('ajax/search-teams/', views.ajax_search_teams, name='ajax_search_teams'),
    path('ajax/partidos/<int:match_id>/resultado/', views.ajax_add_match_result, name='ajax_add_match_result'),
    path('ajax/partidos/<int:match_id>/alineacion/', views.ajax_acta_lineup, name='ajax_acta_lineup'),
]
```
En `config/urls.py`:
```python
    path('competitions/', include('videosvoley.competitions.urls', namespace='competitions')),
```

- [ ] **Step 4: Mover templates a `videosvoley/competitions/templates/competitions/` y actualizar referencias**

Mover los templates de ligas, partidos, calendario y clasificaciones.
Actualizar en templates y código Python:
- `videos:league_*` -> `competitions:league_*`
- `videos:match_detail` -> `competitions:match_detail`
- `videos:calendar_*` -> `competitions:calendar_*`
- `videos:standings_view` -> `competitions:standings_view`
- `videos:friendly_match_create` -> `competitions:friendly_match_create`
- `videos:ajax_matches_by_category` -> `competitions:ajax_matches_by_category`
- `videos:ajax_teams_by_league_category` -> `competitions:ajax_teams_by_league_category`
- `videos:ajax_search_teams` -> `competitions:ajax_search_teams`
- `videos:ajax_add_match_result` -> `competitions:ajax_add_match_result`
- `videos:ajax_acta_lineup` -> `competitions:ajax_acta_lineup`

- [ ] **Step 5: Ejecutar test de barrido y suite de tests**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/core/tests/test_url_reverse_sweep.py -v --tb=short`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: todos los tests pasando en verde.

- [ ] **Step 6: Commit**

```bash
git add videosvoley/competitions/ videosvoley/videos/ config/urls.py videosvoley/templates/
git commit -m "feat(competitions): mudar vistas, formularios, urls y templates de competitions #68 @time 40m"
```

---

### Task 5: Mudanza de páginas y moderación a `core`, y retirada de residuo `videos/templates`

**Files:**
- Move: `videosvoley/templates/videos/about.html` -> `videosvoley/core/templates/core/about.html`
- Move: `videosvoley/templates/videos/moderation_panel.html` -> `videosvoley/core/templates/core/moderation_panel.html`
- Modify: `videosvoley/core/views.py` (añadir `about`, `moderation_panel`, `moderation_counts_api`, `approve_user_api`, `reject_user_api`)
- Modify: `videosvoley/core/urls.py` (registrar `about`, `moderation_panel`, etc.)
- Modify: `videosvoley/videos/views/pages.py` y `videosvoley/videos/views/moderation.py` (re-exportar desde `core.views`)
- Modify: `config/urls.py` (redirección o alias para `/videos/` preservando bookmarks hacia `content:video_list`)
- Delete: `videosvoley/templates/videos/` (debe quedar vacío)
- Modify: Actualizar `videos:about` -> `core:about` y `videos:moderation_panel` -> `core:moderation_panel`

**Interfaces:**
- Consumes: Vistas restantes de `videos`.
- Produces: `videosvoley/templates/videos/` eliminado; cero referencias `videos:` en el proyecto.

- [ ] **Step 1: Trasladar `about` y vistas de moderación de usuarios a `videosvoley/core/`**

Mover lógica de `about` y de moderación de usuarios/panel a `videosvoley/core/views.py`.
Renderizar `'core/about.html'` y `'core/moderation_panel.html'`.
Re-exportar en `videosvoley/videos/views/pages.py` y `videosvoley/videos/views/moderation.py`.

- [ ] **Step 2: Mover templates a `videosvoley/core/templates/core/`**

Mover:
- `videosvoley/templates/videos/about.html` -> `videosvoley/core/templates/core/about.html`
- `videosvoley/templates/videos/moderation_panel.html` -> `videosvoley/core/templates/core/moderation_panel.html`

- [ ] **Step 3: Añadir rutas a `videosvoley/core/urls.py` y actualizar templates**

Añadir en `videosvoley/core/urls.py`:
```python
    path('quienes-somos/', views.about, name='about'),
    path('moderacion/', views.moderation_panel, name='moderation_panel'),
    path('api/moderation/counts/', views.moderation_counts_api, name='moderation_counts_api'),
    path('api/users/<int:user_id>/approve/', views.approve_user_api, name='approve_user_api'),
    path('api/users/<int:user_id>/reject/', views.reject_user_api, name='reject_user_api'),
```
Actualizar en todos los templates y código:
- `videos:about` -> `core:about`
- `videos:moderation_panel` -> `core:moderation_panel`
- `videos:moderation_counts_api` -> `core:moderation_counts_api`
- `videos:approve_user_api` -> `core:approve_user_api`
- `videos:reject_user_api` -> `core:reject_user_api`

- [ ] **Step 4: Eliminar directorio vacío `videosvoley/templates/videos/`**

Verificar que `videosvoley/templates/videos/` está vacío:
Run: `ls videosvoley/templates/videos/`
Expected: vacío.
Eliminar el directorio: `rm -rf videosvoley/templates/videos/`.

- [ ] **Step 5: En `config/urls.py`, añadir redirección de `/videos/` a `content:video_list`**

En `config/urls.py`:
```python
    path('videos/', RedirectView.as_view(pattern_name='content:video_list', permanent=False)),
```

- [ ] **Step 6: Verificar con grep que no queda ninguna referencia a `videos:`**

Run: `grep -rn "videos:" videosvoley/templates/`
Expected: 0 coincidencias.
Run: `grep -rn "videos:" videosvoley/ --exclude-dir=migrations --exclude-dir=tests`
Expected: 0 coincidencias.

- [ ] **Step 7: Ejecutar test de barrido y suite completa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest videosvoley/core/tests/test_url_reverse_sweep.py -v --tb=short`
Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 100% pasando en verde.

- [ ] **Step 8: Commit**

```bash
git add videosvoley/core/ videosvoley/videos/ config/urls.py videosvoley/templates/
git commit -m "feat(core): mudar about y moderacion a core, eliminar residuo templates/videos #68 @time 30m"
```

---

### Task 6: Verificación final de la Fase 4

**Files:**
- None (verificación global de integridad)
- Modify: `docs/superpowers/plans/2026-09-19-refactor-videos-fase-4.md` (marcar checklist)

**Interfaces:**
- Consumes: Todo el trabajo completado en las tareas 0-5.
- Produces: Certificación de que las vistas, URLs y templates están completamente desacoplados sin regresiones.

- [ ] **Step 1: Ejecutar check del sistema**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py check`
Expected: 0 issues.

- [ ] **Step 2: Verificar que no hay migraciones pendientes**

Run: `docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 3: Ejecutar suite completa con `--create-db`**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -v --tb=short`
Expected: 100 tests pasando en verde (98 anteriores + 2 de barrido estático).

- [ ] **Step 4: Commit de documentación y checklist**

```bash
git add docs/superpowers/plans/2026-09-19-refactor-videos-fase-4.md
git commit -m "docs: completar checklist de verificacion de fase 4 #68 @time 10m"
```
