# Sistema de Scraping para Federación de Voleibol

## Descripción General

Este sistema permite obtener automáticamente datos de ligas de voleibol desde la Federación Balear de Voleibol (voleibolib.net) y otras federaciones similares. El sistema es completamente dinámico y configurable desde el Django admin.

## Arquitectura del Sistema

### Modelos de Datos

- **`League`**: Representa una competición/liga
- **`Team`**: Equipos participantes 
- **`Match`**: Partidos entre equipos
- **`Standing`**: Clasificaciones de liga
- **`ScrapingEndpoint`**: Configuración de endpoints para scraping
- **`Video`**: Videos vinculados a partidos específicos

### Componentes de Scraping

- **`BaseParser`**: Clase base para todos los parsers
- **`StandingsParser`**: Parser para tablas de clasificación
- **`MatchesParser`**: Parser para calendarios y resultados
- **`FederationScraper`**: Coordinador principal del scraping

## Configuración de Nueva Liga

### 1. Usando Management Command (Recomendado)

```bash
docker-compose exec web python manage.py setup_league \
  --name "Senior Masculino - Grupo 1" \
  --federation-id 7998 \
  --season "2024-25" \
  --competition-type regular \
  --base-url "https://www.voleibolib.net"
```

**Después de crear la liga:**
1. Ir a Django Admin → Ligas
2. Vincular la liga a una **Categoría** (Senior, Cadete, Infantil, etc.)
3. Esto permite filtrado inteligente en formularios de video

### 2. Desde Django Admin

1. Ir a `/admin/videos/league/add/`
2. Completar los campos:
   - **Nombre**: Nombre descriptivo de la liga
   - **Federation ID**: ID usado en las URLs de la federación
   - **Temporada**: Ej: "2024-25"
   - **Tipo de competición**: regular, playoff, cup, friendly
   - **URL base**: URL base del sitio (por defecto: https://www.voleibolib.net)

3. Crear endpoints en `/admin/videos/scrapingendpoint/add/`:

   **Para Clasificaciones:**
   - Liga: (seleccionar la liga creada)
   - Tipo de endpoint: Clasificación
   - Patrón URL: `JSON/get_clasificacion.asp?id={league_id}`
   - Tipo de parser: Tabla de Clasificación

   **Para Resultados:**
   - Liga: (seleccionar la liga creada)
   - Tipo de endpoint: Resultados
   - Patrón URL: `JSON/get_resultados.asp?id={league_id}&f={round}`
   - Tipo de parser: Resultados de Partidos

## Ejecución de Scraping

### Scraping de Múltiples Ligas (NUEVO)

```bash
# Scraping de TODAS las ligas activas
docker-compose exec web python manage.py scrape_all_leagues --verbose

# Scraping solo de una categoría específica
docker-compose exec web python manage.py scrape_all_leagues --category "Senior" --verbose
docker-compose exec web python manage.py scrape_all_leagues --category "Cadete" --verbose

# Con delay personalizado entre ligas (para ser más respetuoso)
docker-compose exec web python manage.py scrape_all_leagues --delay 3.0
```

### Scraping Manual (Individual)

```bash
# Scraping completo de una liga
docker-compose exec web python manage.py scrape_league --league-id 7998 --verbose

# Scraping de una jornada específica (para endpoints que lo soporten)
docker-compose exec web python manage.py scrape_league --league-id 7998 --round 5
```

### Automatización

Para scraping automático, puedes usar cron:

```bash
# Scraping de todas las ligas diario a las 20:00
0 20 * * * cd /path/to/project && docker-compose exec -T web python manage.py scrape_all_leagues

# O scraping individual por liga
0 20 * * * cd /path/to/project && docker-compose exec -T web python manage.py scrape_league --league-id 7998
```

O configurar Celery para tareas programadas (opcional).

## Estructura de URLs de la Federación

### Patrones Comunes

- **Clasificaciones**: `JSON/get_clasificacion.asp?id={league_id}`
- **Resultados**: `JSON/get_resultados.asp?id={league_id}&f={round}`
- **Calendario**: Similar a resultados pero con partidos futuros

### Parámetros Dinámicos

- `{league_id}`: ID de la federación de la liga
- `{round}`: Número de jornada (opcional)
- Parámetros adicionales se pueden configurar en `extra_params` (JSON)

## Gestión de Equipos

### Normalización de Nombres

El sistema maneja automáticamente:
- Caracteres especiales y acentos (ó → o, à → a)
- Espacios extra
- Diferencias de mayúsculas/minúsculas
- Variaciones menores en nombres

### Búsqueda Inteligente

Si no encuentra un equipo exacto, el sistema:
1. Busca por nombre normalizado
2. Busca por similitud parcial
3. Registra warnings para revisión manual

## Configuración Avanzada

### Endpoints Personalizados

Para federaciones con estructura diferente:

1. Crear nuevo endpoint en admin
2. Especificar patrón URL personalizado
3. Seleccionar parser apropiado o crear uno nuevo

### Rate Limiting

Por defecto: 1 segundo entre requests. Modificable en `BaseParser.rate_limit()`.

### Logging

Configurar nivel de logging en settings:

```python
LOGGING = {
    'loggers': {
        'videosvoley.videos.scraping': {
            'level': 'INFO',
            'handlers': ['console'],
        },
    },
}
```

## Integración con Videos

### Filtrado Inteligente por Categoría y Equipo

El sistema ahora filtra **automáticamente por categoría y equipo del club**:

#### **Configuración Multi-Equipo**
```python
# En settings.py
CLUB_TEAM_NAMES = {
    'default': 'SANT JOSEP',
    'senior': ['SANT JOSEP', 'CV SANT JOSEP'],
    'cadete': ['SANT JOSEP CADETE', 'CV SANT JOSEP CADETE'],
    'infantil': ['SANT JOSEP INFANTIL', 'CV SANT JOSEP INFANTIL'],
}
```

#### **Funcionamiento**
- **Sin categoría**: Muestra partidos de todos los equipos del club
- **Con categoría**: Solo muestra partidos de esa categoría específica
- **Búsqueda inteligente**: Reconoce variaciones del nombre del equipo

### Vincular Videos a Partidos

1. Al crear/editar video, seleccionar partido en campo "Partido (opcional)"
2. **Solo aparecen partidos del equipo configurado** (SANT JOSEP)
3. Los videos aparecerán automáticamente en vistas de partido
4. Filtros disponibles por liga/equipo en lista de videos

### Cambiar Equipo Principal

Para cambiar el equipo que aparece en el formulario:

1. Editar `config/settings.py`
2. Cambiar `CLUB_TEAM_NAME = 'NUEVO_NOMBRE'`
3. Reiniciar servidor Django

### Nuevas Vistas

- `/videos/ligas/`: Lista de todas las ligas
- `/videos/ligas/{id}/`: Detalle de liga con partidos y clasificación
- `/videos/partidos/{id}/`: Detalle de partido con videos

## Solución de Problemas

### Errores Comunes

**"No module named 'bs4'"**
```bash
docker-compose exec web pip install beautifulsoup4
```

**"value too long for type character varying(50)"**
- Aumentar tamaño de campo `federation_id` en migración

**"Teams not found"**
- Verificar nombres de equipos en logs
- Comprobar normalización de caracteres especiales

### Debugging

```bash
# Scraping con logs detallados
docker-compose exec web python manage.py scrape_league --league-id 7998 --verbose

# Verificar contenido de endpoint
curl "https://www.voleibolib.net/JSON/get_clasificacion.asp?id=7998"
```

## Mantenimiento

### Actualización de Datos

- El scraping actualiza datos existentes sin duplicar
- Las clasificaciones se reemplazan completamente
- Los partidos se actualizan o crean según `federation_id`

### Limpieza de Datos

```bash
# Eliminar liga y todos sus datos relacionados
# (Cuidado: esto borra todo)
docker-compose exec web python manage.py shell
>>> from videosvoley.videos.models import League
>>> League.objects.get(federation_id='7998').delete()
```

### Backup

Respaldar regularmente la base de datos:

```bash
docker-compose exec db pg_dump -U volleyuser volleyvideos > backup.sql
```

## Extensibilidad

### Nuevos Parsers

Para estructuras HTML diferentes:

1. Crear nueva clase heredando de `BaseParser`
2. Implementar método `parse_content()`
3. Añadir a `PARSER_TYPES` en `ScrapingEndpoint`
4. Registrar en `FederationScraper.parsers`

### Otras Federaciones

El sistema está diseñado para funcionar con cualquier federación que use estructura similar:
- URLs con parámetros
- Respuestas HTML tabulares
- Estructura consistente

## Ejemplo Completo: Club Multi-Categoría

```bash
# 1. Configurar múltiples ligas
docker-compose exec web python manage.py setup_league \
  --name "Senior Masculino" --federation-id 7998 --season "2024-25"

docker-compose exec web python manage.py setup_league \
  --name "Cadete Masculino" --federation-id 8001 --season "2024-25"

docker-compose exec web python manage.py setup_league \
  --name "Infantil Masculino" --federation-id 8002 --season "2024-25"

# 2. Vincular ligas a categorías en Django Admin
# Senior Masculino → Categoría "Senior"
# Cadete Masculino → Categoría "Cadete" 
# Infantil Masculino → Categoría "Infantil"

# 3. Ejecutar scraping de todas las ligas
docker-compose exec web python manage.py scrape_all_leagues --verbose

# 4. Verificar datos en admin: http://localhost:8000/admin/

# 5. Programar scraping automático diario
0 22 * * * cd /path/to/project && docker-compose exec -T web python manage.py scrape_all_leagues

# 6. Scraping por categorías específicas
docker-compose exec web python manage.py scrape_all_leagues --category "Senior"
```

### **Resultado:**
- **Videos de Senior**: Solo muestran partidos de senior de SANT JOSEP
- **Videos de Cadete**: Solo muestran partidos de cadete de SANT JOSEP  
- **Admin completo**: Ve todos los partidos para gestión integral

## Notas Importantes

- ⚠️ **Respetar rate limiting**: No hacer requests muy frecuentes
- 📊 **Verificar datos**: Revisar logs para detectar problemas
- 🔄 **Backup regular**: Los datos se actualizan automáticamente
- 🆕 **Nuevas fases**: Configurar endpoints adicionales cuando aparezcan liguillas
- 📱 **Monitoreo**: Verificar que las URLs de federación no cambien

## Soporte

Para problemas o nuevas funcionalidades:
1. Revisar logs de scraping
2. Verificar configuración de endpoints
3. Comprobar estructura HTML de la federación
4. Consultar este documento para configuración avanzada