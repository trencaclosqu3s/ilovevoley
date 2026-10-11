# Sistema de Filtros Automáticos

## Descripción

Sistema de filtros que se aplican automáticamente al cambiar su valor, sin necesidad de pulsar un botón "Aplicar filtros". Mejora la experiencia de usuario al proporcionar feedback inmediato.

En la aplicación conviven dos patrones complementarios de auto-filtrado:

1. **`auto_filters.js` (clase CSS `.auto-filter`)**: manipula directamente la URL (`window.location.search`) y recarga la página. Soporta debounce en campos de texto, resetea la paginación (`page`) y gestiona checkboxes con valores desmarcados.
2. **`data-submit-on-change` (manejador global `csp_actions.js`)**: delega el evento `change` para invocar nativamente `form.submit()`. Es la solución preferida para formularios estructurados con soporte progresivo (botón "Filtrar" para fallback sin JS) y formularios complejos con múltiples campos repetidos (ej. selección múltiple de equipos mediante chips en Resultados).

---

## Características

- ✅ Aplicación automática de filtros al cambiar el valor
- ✅ Dos mecanismos estándar según la complejidad del formulario (`.auto-filter` vs `data-submit-on-change`)
- ✅ Indicador visual de carga en `auto_filters.js` mientras se aplica el filtro
- ✅ Compatible con `<select>`, `<input type="text">` y `<input type="checkbox">`
- ✅ Debounce automático para campos de texto (500ms en `auto_filters.js`)
- ✅ Limpieza automática de la paginación (`page`) al filtrar
- ✅ Preservación de otros parámetros de URL existentes
- ✅ Contrato compatible con `resolve_season_filter` para "Todas las temporadas" (`season=`)
- ✅ Progressive Enhancement: botones "Filtrar" conservados como fallback accesible sin JavaScript cuando se requiere

---

## Contrato de `season=` y `resolve_season_filter`

La convención de temporadas en el backend está centralizada en `ilovevoley.core.season_utils.resolve_season_filter(request)`:

- **Sin parámetro** (`season` ausente de la query string): el backend asume la **temporada activa** (`Season.objects.current()`).
- **Parámetro vacío** (`?season=`): el usuario ha elegido explícitamente **"Todas las temporadas"**, devolviendo `(None, '')`.
- **ID numérico** (`?season=5`): filtra por la temporada con esa clave primaria.

### Implicación en `auto_filters.js`

Dado que la ausencia del parámetro reactiva la temporada por defecto, `auto_filters.js` tiene una regla específica para el filtro `season`:

- Para cualquier otro filtro con valor vacío/nulo, el parámetro se elimina de la URL (`url.searchParams.delete(filterName)`).
- **Para `filterName === 'season'`**, cuando el valor es vacío o nulo, **no se borra**, sino que se fija como cadena vacía: `url.searchParams.set('season', '')`. De esta forma la URL resultante es `?season=`, indicando fielmente al backend que se deben listar todas las temporadas.

En formularios con `data-submit-on-change`, el navegador envía de forma nativa `season=` cuando la opción seleccionada tiene `value=""`, cumpliendo el mismo contrato sin lógica adicional.

---

## Inventario de Vistas y Filtros

### 1. Páginas con `auto_filters.js` (`.auto-filter`)

Vistas que incluyen `<script src="{% static 'js/auto_filters.js' %}"></script>` y aplican la clase `auto-filter` en sus inputs/selects:

| Vista | Módulo / Función | Template | Filtros automáticos |
|---|---|---|---|
| **Lista de Ligas** | `ilovevoley.competitions.views.league_list` | `competitions/templates/competitions/league_list.html` | Categoría (`category`), amistosos (`show_friendly`), temporadas pasadas (`show_past`) |
| **Galería de Imágenes** | `ilovevoley.content.views.image_gallery` | `content/templates/content/image_gallery.html` | Búsqueda (`search`, con debounce), categoría (`category`), temporada (`season`), estado de moderación (`status`) |
| **Lista de Vídeos** | `ilovevoley.content.views.video_list` | `content/templates/content/video_list.html` | Búsqueda (`search`, con debounce), categoría (`category`), temporada (`season`) |
| **Calendario de Partidos** | `ilovevoley.competitions.views.calendar_view` | `competitions/templates/competitions/calendar.html` | Categoría (`category`), liga (`league`), checkbox "Todos los equipos" (`all_teams`) |
| **Clasificación** | `ilovevoley.competitions.views.standings_view` | `competitions/templates/competitions/standings.html` | Liga (`league`), temporada por nombre (`season_name`), archivadas (`show_archived`) |
| **Directorio de Personas** | `ilovevoley.rosters.views.person_list` | `rosters/templates/rosters/person_list.html` | Búsqueda (`search`, con debounce), tipo de rol (`role_type`) |
| **Visión Global de Plantillas** | `ilovevoley.rosters.views.roster_overview` | `rosters/templates/rosters/roster_overview.html` | Categoría (`category`), temporada (`season`) |

### 2. Páginas con `data-submit-on-change` (`csp_actions.js`)

Vistas cuyos controles de formulario llevan el atributo `data-submit-on-change`. El listener delegado en `static/js/csp_actions.js` ejecuta `el.form.submit()` al producirse el evento `change`:

| Vista | Módulo / Función | Template | Filtros automáticos |
|---|---|---|---|
| **Resultados** | `ilovevoley.competitions.views.results_view` | `competitions/templates/competitions/results.html` | Periodo (`period`), temporada (`season`), categoría (`category`), checkbox todos los equipos (`all_teams`), y chips dinámicos de equipos (`teams`) mediante `results.js` |
| **Detalle de Liga** | `ilovevoley.competitions.views.league_detail` | `competitions/templates/competitions/league_detail.html` | Jornada (`round`), solo con vídeos (`with_videos`) |
| **Portal de Competiciones** | `ilovevoley.competitions.portal_views.*` | `competitions/templates/competitions/portal/base_portal.html`, `_league_filter.html`, `standings.html` | Temporada (`season`), liga (`league`) |
| **Revisión de Cambios de Partidos** | `ilovevoley.competitions.views.match_changes_review` | `competitions/templates/competitions/match_changes_review.html` | Temporada (`season`), tipo de cambio (`type`) |
| **Lista de Equipos** | `ilovevoley.teams.views.team_list` | `teams/templates/teams/team_list.html` | Categoría (`category`), temporada (`season`), checkbox mostrar todas (`show_all`) |
| **Plantilla de Equipo** | `ilovevoley.teams.views.team_roster` | `teams/templates/teams/team_roster.html` | Temporada (`season`); además, enlaces de posición (`position`) y rol (`role`) combinables de forma no excluyente |
| **Ficha de Persona** | `ilovevoley.rosters.views.person_detail` | `rosters/templates/rosters/person_detail.html` | Temporada (`season`) |
| **Season Wrapped** | `ilovevoley.rosters.views.season_wrapped_page` | `rosters/templates/rosters/season_wrapped.html` | Temporada (`season`), modalidad (`modality`) |

### 3. Vistas manuales antes de este PR (#509) y estado actual

- **Resultados de Partidos (`competitions:results`)**:
  - *Antes*: requería hacer clic en el botón "Filtrar" tras modificar selects o checkboxes. Añadir o eliminar chips de equipos no recargaba automáticamente la lista.
  - *Ahora*: selects de periodo, temporada y categoría, así como el checkbox de todos los equipos, usan `data-submit-on-change`. Añadir o quitar chips de equipos invoca `form.submit()` mediante `results.js`. Se mantiene el botón "Filtrar" como fallback sin JavaScript.
- **Lista de Equipos (`teams:team_list`)**:
  - *Antes*: requería pulsar botón de envío para aplicar filtros de categoría o temporada.
  - *Ahora*: selects y checkbox disponen de `data-submit-on-change`.
- **Detalle de Liga (`competitions:league_detail`)**:
  - *Antes*: el selector de jornada (`round`) y el checkbox «solo con vídeos» requerían pulsar «Filtrar».
  - *Ahora*: integrados con `data-submit-on-change`.
- **Plantilla de Equipo (`teams:team_roster`)**:
  - *Antes*: el select de temporada tenía clase `auto-filter` pero no cargaba el script; los chips de posición y rol se pisaban entre sí en la query string.
  - *Ahora*: temporada con `data-submit-on-change`; los enlaces preservan `season`, `position` y `role` sin exclusión mutua.
- **Vistas manuales / híbridas por diseño**:
  - **Sedes (`competitions:where_plays`)**: buscador con debounce AJAX (`where_plays.js`); el botón «Buscar» no es el flujo principal con JS.
  - **Alta masiva de plantilla (`rosters:roster_bulk_add`)**: el select de temporada ya hace submit on change (precarga); el buscador de personas es filtro en cliente.

---

## Guía de Uso e Implementación

### Opción 1: Formulario con `data-submit-on-change` (Recomendada para formularios estándar)

Adecuada si la vista tiene un formulario `GET` con varios campos o chips dinámicos:

```html
<form method="get" class="space-y-4">
    <!-- Select con envío automático -->
    <select name="season" data-submit-on-change class="...">
        <option value="" {% if not selected_season %}selected{% endif %}>Todas las temporadas</option>
        {% for s in seasons %}
            <option value="{{ s.id }}" {% if selected_season == s.id|stringformat:"s" %}selected{% endif %}>{{ s.name }}</option>
        {% endfor %}
    </select>

    <!-- Checkbox con envío automático -->
    <input type="checkbox" name="all_teams" value="1" {% if show_all_teams %}checked{% endif %} data-submit-on-change>

    <!-- Botón fallback accesible sin JS -->
    <button type="submit" class="...">Filtrar</button>
</form>
```

No requiere JS adicional si `csp_actions.js` está incluido en la plantilla base.

---

### Opción 2: Filtros directos con `auto_filters.js` (`.auto-filter`)

Adecuada para barras de filtrado sin formulario tradicional o con inputs de texto con debounce:

```django
{% block extra_js %}
<script src="{% static 'js/auto_filters.js' %}"></script>
{% endblock %}
```

```html
<!-- Input con debounce de 500ms -->
<input type="text" name="search" class="auto-filter" placeholder="Buscar..." value="{{ search_query }}">

<!-- Select con recarga inmediata -->
<select name="category" class="auto-filter">
    <option value="">Todas las categorías</option>
    {% for cat in categories %}
        <option value="{{ cat.id }}" {% if selected_category == cat.id|stringformat:"s" %}selected{% endif %}>
            {{ cat.name }}
        </option>
    {% endfor %}
</select>

<!-- Select de temporada (respeta season= para 'Todas') -->
<select name="season" class="auto-filter">
    <option value="">Todas las temporadas</option>
    {% for s in seasons %}
        <option value="{{ s.id }}" {% if selected_season == s.id|stringformat:"s" %}selected{% endif %}>
            {{ s.name }}
        </option>
    {% endfor %}
</select>
```
