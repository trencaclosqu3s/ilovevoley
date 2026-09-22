# Sistema de Scraping Avanzado - Ligas Históricas y Externas

## Descripción General

El sistema de scraping ha sido expandido para soportar diferentes tipos de ligas con control granular de visibilidad:

- **Ligas Principales**: Se muestran en la aplicación principal (comportamiento actual)
- **Ligas de Referencia**: Solo visibles en admin, relacionadas con nuestro equipo
- **Ligas Históricas**: Datos de temporadas anteriores, solo admin
- **Ligas Externas**: Otras ligas no relacionadas con nuestro equipo, solo admin

## Nuevos Campos del Modelo League

### Campos de Visibilidad
- `visibility_type`: Controla dónde se muestra la liga
- `is_historical`: Indica si es una liga de temporadas anteriores
- `is_our_team_related`: Indica si está relacionada con nuestro equipo

### Tipos de Visibilidad
1. **main**: Principal (mostrar en app)
2. **reference**: Referencia (solo admin)
3. **historical**: Histórica (solo admin)
4. **external**: Externa (solo admin)

## Comandos de Gestión

### 1. Scraping de Ligas Históricas

```bash

# Scraping masivo de ligas históricas
docker-compose exec web python manage.py scrape_historical_leagues \
    --visibility-type historical \
    --verbose

# Modo dry-run para probar
docker-compose exec web python manage.py scrape_historical_leagues \
    --visibility-type historical \
    --dry-run \
    --verbose
```

### 2. Scraping de Ligas Externas

```bash
# Scraping masivo de ligas externas
docker-compose exec web python manage.py scrape_external_leagues \
    --federation-base-url "https://www.voleibolib.net" \
    --season "2024-25" \
    --category "Senior" \
    --competition-type regular \
    --max-leagues 20 \
    --verbose

# Scraping de liga externa específica
docker-compose exec web python manage.py scrape_external_leagues \
    --federation-base-url "https://www.voleibolib.net" \
    --season "2024-25" \
    --category "Senior" \
    --dry-run \
    --verbose
```

### 3. Scraping de Ligas de Referencia

```bash
# Crear ligas de referencia para análisis
docker-compose exec web python manage.py scrape_historical_leagues \
    --league-id "2001" \
    --season "2024-25" \
    --visibility-type reference \
    --league-name "Liga Catalana Senior" \
    --category "Senior" \
    --verbose
```

## Configuración en Admin

### Gestión de Ligas
1. Acceder a `/admin/videos/league/`
2. Usar filtros por `visibility_type` para organizar ligas
3. Usar acciones masivas para cambiar tipos de ligas:
   - Marcar como ligas principales
   - Marcar como ligas de referencia
   - Marcar como ligas históricas
   - Marcar como ligas externas

### Campos Editables
- `visibility_type`: Tipo de visibilidad
- `is_our_team_related`: Relación con nuestro equipo
- `is_historical`: Si es histórica
- `is_active`: Estado activo

## Casos de Uso

### 1. Análisis Estadístico
```python
# Obtener todas las ligas para análisis
from ilovevoley.videos.models import League

# Ligas principales (visibles en app)
main_leagues = League.objects.visible_in_app()

# Ligas de referencia (solo admin)
reference_leagues = League.objects.reference_leagues()

# Ligas históricas
historical_leagues = League.objects.historical_leagues()

# Ligas externas
external_leagues = League.objects.external_leagues()

# Todas las ligas para admin
all_leagues = League.objects.all_for_admin()
```

### 2. Scraping de Datos Históricos
```bash
# Scraping de temporadas anteriores
docker-compose exec web python manage.py scrape_historical_leagues \
    --league-id "1234" \
    --season "2022-23" \
    --visibility-type historical \
    --league-name "Liga Nacional 2022-23" \
    --category "Senior" \
    --delay 2.0 \
    --verbose
```

### 3. Análisis de Competencia
```bash
# Scraping de ligas de otros equipos/regiones
docker-compose exec web python manage.py scrape_external_leagues \
    --federation-base-url "https://www.voleibolib.net" \
    --season "2024-25" \
    --category "Senior" \
    --max-leagues 10 \
    --delay 3.0 \
    --verbose
```

## Configuración de Endpoints Históricos

### Endpoints Conocidos
```python
# Ejemplo de configuración para endpoints históricos
historical_endpoints = [
    {
        'federation_id': '1234',
        'name': 'Liga Nacional 2023-24',
        'season': '2023-24',
        'category': 'Senior',
        'base_url': 'https://www.voleibolib.net',
        'visibility_type': 'historical'
    },
    {
        'federation_id': '1235',
        'name': 'Liga Nacional 2022-23',
        'season': '2022-23',
        'category': 'Senior',
        'base_url': 'https://www.voleibolib.net',
        'visibility_type': 'historical'
    }
]
```

## Ventajas del Sistema

### 1. **Separación de Datos**
- Datos principales vs datos de referencia
- Control granular de visibilidad
- Organización clara por tipo de liga

### 2. **Análisis Estadístico**
- Base de datos completa para análisis
- Comparación con ligas externas
- Datos históricos para tendencias

### 3. **Gestión Eficiente**
- Comandos especializados por tipo
- Interfaz admin mejorada
- Acciones masivas

### 4. **Escalabilidad**
- Fácil agregar nuevas ligas
- Configuración flexible
- Rate limiting integrado

## Consideraciones Técnicas

### Rate Limiting
- Delay configurable entre requests
- Respeto a APIs externas
- Manejo de errores robusto

### Almacenamiento
- Datos históricos no afectan rendimiento de app principal
- Filtrado eficiente en vistas
- Indexación optimizada

### Monitoreo
- Logging detallado
- Modo dry-run para pruebas
- Resumen de operaciones

## Próximos Pasos

1. **Configurar endpoints históricos específicos**
2. **Ejecutar scraping inicial de datos históricos**
3. **Configurar scraping periódico de ligas externas**
4. **Implementar análisis estadístico avanzado**
5. **Crear dashboards de análisis en admin**

## Comandos de Mantenimiento

```bash
# Verificar estado de ligas
docker-compose exec web python manage.py shell
>>> from ilovevoley.videos.models import League
>>> League.objects.filter(visibility_type='external').count()
>>> League.objects.filter(visibility_type='historical').count()

# Limpiar ligas externas antiguas (opcional)
>>> League.objects.filter(visibility_type='external', is_active=False).delete()

# Activar ligas históricas para análisis
>>> League.objects.filter(visibility_type='historical').update(is_active=True)
```
