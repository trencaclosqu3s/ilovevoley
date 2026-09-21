# Sistema de Filtros Automáticos

## Descripción

Sistema genérico de filtros que se aplican automáticamente al cambiar su valor, sin necesidad de pulsar un botón "Aplicar filtros". Mejora la experiencia de usuario al proporcionar feedback inmediato.

## Características

- ✅ Aplicación automática de filtros al cambiar el valor
- ✅ Indicador visual de carga mientras se aplica el filtro
- ✅ Compatible con `<select>`, `<input type="text">` y `<input type="checkbox">`
- ✅ Debounce automático para campos de texto (evita múltiples peticiones - 500ms)
- ✅ Limpia automáticamente la paginación al filtrar
- ✅ Mantiene otros parámetros de URL existentes (year, month, view, etc.)
- ✅ Totalmente genérico y reutilizable
- ✅ **Se eliminaron todos los botones "Filtrar" - ya no son necesarios**

## Implementación

### 1. Backend (Vista de Django)

En tu vista, asegúrate de:

```python
def mi_vista(request):
    # Obtener datos base
    items = MiModelo.objects.all()
    
    # Obtener opciones para el filtro
    categorias = Categoria.objects.filter(is_active=True).order_by('name')
    
    # Obtener parámetro del filtro
    categoria_filter = request.GET.get('category')
    
    # Aplicar filtro si existe
    if categoria_filter:
        items = items.filter(category_id=categoria_filter)
    
    # Retornar al template
    return render(request, 'mi_template.html', {
        'items': items,
        'categorias': categorias,
        'selected_category': categoria_filter,  # Para marcar la opción seleccionada
    })
```

### 2. Template (HTML)

#### a) Incluir el script de auto_filters.js

En tu template, agrega el bloque `extra_js`:

```django
{% extends 'base.html' %}
{% load static %}

{% block extra_js %}
<script src="{% static 'js/auto_filters.js' %}"></script>
{% endblock %}
```

#### b) Crear el elemento de filtro

Para un `<select>`:

```html
<div class="flex-1">
    <label for="category-filter" class="block text-sm font-medium text-gray-700 mb-1">
        Filtrar por categoría
    </label>
    <select id="category-filter" 
            name="category" 
            class="auto-filter w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-csj-purple focus:border-transparent">
        <option value="">Todas las categorías</option>
        {% for categoria in categorias %}
            <option value="{{ categoria.id }}" 
                    {% if selected_category|stringformat:"s" == categoria.id|stringformat:"s" %}selected{% endif %}>
                {{ categoria.name }}
            </option>
        {% endfor %}
    </select>
</div>
```

Para un `<input type="text">` (con debounce de 500ms):

```html
<div class="flex-1">
    <label for="search-filter" class="block text-sm font-medium text-gray-700 mb-1">
        Buscar
    </label>
    <input type="text" 
           id="search-filter" 
           name="search" 
           class="auto-filter w-full px-3 py-2 border border-gray-300 rounded-lg"
           placeholder="Buscar..."
           value="{{ search_query|default:'' }}">
</div>
```

### 3. Clase CSS Requerida

Lo único que necesitas hacer es agregar la clase `auto-filter` a cualquier elemento de formulario:

```html
<select name="mi_filtro" class="auto-filter">
    <!-- opciones -->
</select>

<input type="text" name="busqueda" class="auto-filter">

<input type="checkbox" name="activo" class="auto-filter">
```

## Ejemplos de Implementación

El sistema está implementado en las siguientes vistas:

### 1. Lista de Ligas (`league_list`)
- **Vista**: `ilovevoley/videos/views.py` → función `league_list`
- **Template**: `ilovevoley/templates/videos/league_list.html`
- **Filtros**: Categoría

### 2. Galería de Imágenes (`image_gallery`)
- **Vista**: `ilovevoley/videos/views.py` → función `image_gallery`
- **Template**: `ilovevoley/templates/videos/image_gallery.html`
- **Filtros**: Búsqueda de texto, categoría, año, estado (staff)

### 3. Lista de Videos (`video_list`)
- **Vista**: `ilovevoley/videos/views.py` → función `video_list`
- **Template**: `ilovevoley/templates/videos/video_list.html`
- **Filtros**: Búsqueda de texto, categoría

### 4. Calendario de Partidos (`calendar_view`)
- **Vista**: `ilovevoley/videos/views.py` → función `calendar_view`
- **Template**: `ilovevoley/templates/videos/calendar.html`
- **Filtros**: Categoría, liga, checkbox "Todos los equipos"

### 5. Clasificación (`standings_view`)
- **Vista**: `ilovevoley/videos/views.py` → función `standings_view`
- **Template**: `ilovevoley/templates/videos/standings.html`
- **Filtros**: Categoría, liga

**JavaScript común**: `ilovevoley/static/js/auto_filters.js`

## Funcionamiento Interno

1. El script `auto_filters.js` se carga al cargar la página
2. Detecta todos los elementos con clase `auto-filter`
3. Agrega event listeners según el tipo:
   - `change` para `<select>` y otros inputs
   - `input` con debounce para campos de texto
4. Al cambiar el valor:
   - Muestra indicador de carga
   - Actualiza la URL con el nuevo parámetro
   - Elimina el parámetro de página (para volver a página 1)
   - Recarga la página con los nuevos filtros

## Ventajas

- **UX mejorada**: Feedback inmediato sin clicks adicionales
- **Genérico**: Funciona en cualquier vista sin código adicional
- **Mantenible**: Un solo archivo JS para toda la aplicación
- **Compatible**: Funciona con cualquier backend que use parámetros GET
- **Progressive Enhancement**: Si JS está deshabilitado, el formulario sigue funcionando con un botón submit tradicional

## Personalización

### Cambiar el tiempo de debounce

Edita la línea en `auto_filters.js`:

```javascript
}, 500)); // Cambiar 500 a los milisegundos deseados
```

### Modificar el indicador de carga

Edita la función `showLoadingIndicator()` en `auto_filters.js`:

```javascript
spinner.innerHTML = `
    <div class="animate-spin ..."></div>
    <span>Tu mensaje personalizado...</span>
`;
```

### Hacer una petición AJAX en lugar de recargar

Modifica la función `applyFilters()` para usar `fetch()` o `XMLHttpRequest` en lugar de `window.location.href`.

## Compatibilidad con Otros Filtros

Puedes tener múltiples filtros en la misma página:

```html
<!-- Filtro de categoría -->
<select name="category" class="auto-filter">...</select>

<!-- Filtro de año -->
<select name="year" class="auto-filter">...</select>

<!-- Búsqueda por texto -->
<input type="text" name="search" class="auto-filter">
```

Todos funcionarán de forma independiente y se combinarán en la URL.

## Notas Importantes

1. El atributo `name` del elemento es crucial - debe coincidir con el nombre del parámetro GET en tu vista
2. El valor vacío (`""`) elimina el filtro
3. La paginación se resetea automáticamente al cambiar filtros
4. Otros parámetros de URL se mantienen intactos

## Estado Actual

### ✅ Completado
- [x] Sistema genérico de filtros automáticos
- [x] Soporte para `<select>`, `<input type="text">` y `<input type="checkbox">`
- [x] Implementado en todas las vistas principales:
  - [x] Lista de Ligas
  - [x] Galería de Imágenes
  - [x] Lista de Videos
  - [x] Calendario de Partidos
  - [x] Clasificación
- [x] Indicadores visuales de carga
- [x] Debounce para campos de texto
- [x] Preservación de parámetros de URL
- [x] Banners de preferencias de usuario
- [x] Documentación completa

### 🔮 Próximas Mejoras Potenciales
- [ ] Opción para hacer peticiones AJAX sin recargar la página
- [ ] Animaciones de transición entre filtros
- [ ] Historial de filtros aplicados (navegación atrás/adelante)
- [ ] Guardar filtros favoritos del usuario en base de datos
- [ ] Exportar resultados filtrados (PDF/Excel)

