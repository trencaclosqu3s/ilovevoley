/**
 * Sistema genérico de filtros automáticos
 * Aplica filtros sin necesidad de pulsar botón "Aplicar"
 * 
 * Uso:
 * 1. Agregar la clase 'auto-filter' a cualquier select, input o checkbox
 * 2. El script detectará cambios automáticamente y recargará la página con los filtros aplicados
 * 
 * Ejemplo:
 * <select name="category" class="auto-filter">
 *   <option value="">Todas</option>
 *   <option value="1">Categoría 1</option>
 * </select>
 */

document.addEventListener('DOMContentLoaded', function() {
    // Seleccionar todos los elementos con la clase 'auto-filter'
    const autoFilterElements = document.querySelectorAll('.auto-filter');
    
    autoFilterElements.forEach(function(element) {
        // Determinar el tipo de evento según el tipo de elemento
        let eventType = 'change';
        
        if (element.tagName === 'INPUT' && element.type === 'text') {
            // Para inputs de texto, usar 'input' con debounce
            eventType = 'input';
            element.addEventListener(eventType, debounce(function() {
                applyFilters(element);
            }, 500)); // Esperar 500ms después de que el usuario deje de escribir
        } else {
            // Para selects y otros inputs, aplicar inmediatamente
            element.addEventListener(eventType, function() {
                applyFilters(element);
            });
        }
    });
});

/**
 * Aplica los filtros recargando la página con los parámetros actualizados
 */
function applyFilters(changedElement) {
    // Mostrar indicador de carga
    showLoadingIndicator(changedElement);
    
    // Obtener la URL actual
    const url = new URL(window.location);
    
    // Limpiar parámetro de página al cambiar filtros
    url.searchParams.delete('page');
    
    // Actualizar o agregar el parámetro del filtro cambiado
    const filterName = changedElement.name;
    let filterValue;
    
    // Manejar checkboxes de forma especial
    if (changedElement.type === 'checkbox') {
        if (changedElement.checked) {
            filterValue = changedElement.value;
        } else {
            filterValue = changedElement.dataset.uncheckedValue !== undefined ? changedElement.dataset.uncheckedValue : '';
        }
    } else {
        filterValue = changedElement.value;
    }
    
    // Si el elemento define una cookie de persistencia, sincronizarla en el navegador
    if (changedElement.dataset.cookie) {
        const cookieVal = (changedElement.type === 'checkbox') ? (changedElement.checked ? '1' : '0') : (filterValue || '');
        document.cookie = `${changedElement.dataset.cookie}=${cookieVal}; path=/; max-age=31536000; SameSite=Lax`;
    }
    
    if (filterValue === '' || filterValue === null) {
        // Si el valor está vacío, eliminar el parámetro
        url.searchParams.delete(filterName);
    } else {
        // Actualizar el parámetro
        url.searchParams.set(filterName, filterValue);
    }
    
    // Recargar la página con los nuevos parámetros
    window.location.href = url.toString();
}

/**
 * Muestra un indicador visual de que el filtro se está aplicando
 */
function showLoadingIndicator(element) {
    // Agregar clase de loading al elemento
    element.classList.add('opacity-50', 'pointer-events-none');
    
    // Agregar spinner si no existe
    const existingSpinner = document.getElementById('filter-loading-spinner');
    if (existingSpinner) return;
    
    const spinner = document.createElement('div');
    spinner.id = 'filter-loading-spinner';
    spinner.className = 'fixed top-4 right-4 z-50 bg-white rounded-lg shadow-lg p-4 flex items-center space-x-3 animate-pulse';
    spinner.innerHTML = `
        <div class="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-600"></div>
        <span class="text-sm font-medium text-gray-700">Aplicando filtro...</span>
    `;
    
    document.body.appendChild(spinner);
}

/**
 * Función de debounce para evitar múltiples ejecuciones rápidas
 * Útil para campos de texto donde el usuario está escribiendo
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Función auxiliar para obtener todos los filtros activos
 * Útil si necesitas hacer peticiones AJAX en lugar de recargar la página
 */
function getCurrentFilters() {
    const filters = {};
    const autoFilterElements = document.querySelectorAll('.auto-filter');
    
    autoFilterElements.forEach(function(element) {
        const name = element.name;
        const value = element.value;
        
        if (value !== '' && value !== null) {
            filters[name] = value;
        }
    });
    
    return filters;
}

