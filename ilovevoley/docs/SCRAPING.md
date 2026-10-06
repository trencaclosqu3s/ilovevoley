# Sistema de Scraping para Federación de Voleibol

## Descripción General

Este sistema permite obtener automáticamente datos de ligas de voleibol desde la Federación Balear de Voleibol (voleibolib.net) y otras federaciones similares. El sistema es completamente dinámico y configurable desde el Django admin.

## Arquitectura del Sistema

### Modelos de Datos

- **`League`**: Representa una competición/liga
- **`Club`**: Información oficial de clubes (datos de contacto, ubicación, logos)
- **`Team`**: Equipos participantes (pueden incluir patrocinadores)
- **`Match`**: Partidos entre equipos
- **`Standing`**: Clasificaciones de liga
- **`ScrapingEndpoint`**: Configuración de endpoints para scraping
- **`Video`**: Videos vinculados a partidos específicos

### Componentes de Scraping

- **`BaseParser`**: Clase base para todos los parsers
- **`StandingsParser`**: Parser para tablas de clasificación
- **`MatchesParser`**: Parser para calendarios y resultados
- **`FederationScraper`**: Coordinador principal del scraping
- **`ClubScraper`**: Sistema de scraping de clubes con matching inteligente

## Configuración de Nueva Liga

### 1. Usando Management Command (Recomendado)

```bash
# Liga estándar (masculino/femenino - 5 sets, ganar 3)
docker-compose exec web python manage.py setup_league \
  --name "Senior Masculino - Grupo 1" \
  --federation-id 7998 \
  --season "2024-25" \
  --competition-type regular \
  --base-url "https://www.voleibolib.net"

# Liga alevín balear (3 sets, jugar los 3)
docker-compose exec web python manage.py setup_league \
  --name "Alevín Balear - Grupo 1" \
  --federation-id 8000 \
  --season "2024-25" \
  --competition-type regular \
  --match-format alevin_balear

# Torneo especial 3 sets (ganar 2)
docker-compose exec web python manage.py setup_league \
  --name "Torneo 3 Sets" \
  --federation-id 8001 \
  --season "2024-25" \
  --competition-type cup \
  --match-format tournament_3sets

# Formato personalizado
docker-compose exec web python manage.py setup_league \
  --name "Liga Personalizada" \
  --federation-id 8002 \
  --season "2024-25" \
  --competition-type regular \
  --match-format custom \
  --custom-max-sets 4 \
  --custom-sets-to-win 3
```

**Después de crear la liga:**
1. Ir a Django Admin → Ligas
2. Vincular la liga a una **Categoría** (Senior, Cadete, Infantil, etc.)
3. Configurar el **Formato de Partidos** si no se hizo en el comando
4. Esto permite filtrado inteligente en formularios de video y validación de resultados

### 2. Desde Django Admin

1. Ir a `/admin/competitions/league/add/`
2. Completar los campos:
   - **Nombre**: Nombre descriptivo de la liga
   - **Federation ID**: ID usado en las URLs de la federación
   - **Temporada**: Seleccionar o crear la `Season` correspondiente (ej: "2024-25")
   - **Tipo de competición**: regular, playoff, cup, friendly
   - **URL base**: URL base del sitio (por defecto: https://www.voleibolib.net)

> [!NOTE]
> Al guardar la liga en el admin, **los 3 endpoints básicos se crean automáticamente**. Si necesitas personalizarlos, puedes gestionarlos en `/admin/competitions/scrapingendpoint/`.

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

## Validación de Resultados de Voleibol

### Formatos de Partido Soportados

El sistema incluye validación inteligente de resultados según el formato de la liga:

#### **Estándar (Masculino/Femenino)**
- **Formato**: 5 sets máximo, ganar 3
- **Resultados válidos**: 3-0, 3-1, 3-2, 4-3, 5-3, etc.
- **Resultados inválidos**: 0-0, 1-1, 2-2, 3-3, etc.

#### **Alevín Balear**
- **Formato**: 3 sets, jugar los 3 (obligatorio que jueguen todos los niños)
- **Resultados válidos**: 3-0, 2-1, 1-2, 0-3
- **Resultados inválidos**: Cualquier otro resultado

#### **Torneo 3 Sets**
- **Formato**: 3 sets máximo, ganar 2
- **Resultados válidos**: 2-0, 2-1
- **Resultados inválidos**: 0-0, 1-1, 2-2, 3-0, etc.

#### **Personalizado**
- **Formato**: Configurable por el usuario
- **Parámetros**: `custom_max_sets` y `custom_sets_to_win`

### Configuración en Django Admin

1. Ir a **Ligas** → Seleccionar liga
2. En la sección **"Formato de Partidos"**:
   - **Formato de partido**: Seleccionar el formato apropiado
   - **Máximo de sets**: Solo para formato personalizado
   - **Sets necesarios para ganar**: Solo para formato personalizado

### Comportamiento del Sistema

- **Resultados inválidos**: Se rechazan automáticamente y se marcan como programados
- **Logs de validación**: Se registran warnings para resultados inválidos
- **Compatibilidad**: Las ligas existentes usan formato estándar por defecto

### Limpieza de Datos Existentes

```python
# Ejecutar en Django shell para limpiar resultados inválidos existentes
from ilovevoley.competitions.models import Match
from ilovevoley.videos.scraping.parsers import validate_volleyball_score
from django.db import transaction

# Buscar partidos con resultados inválidos
invalid_matches = []
for match in Match.objects.filter(home_score__isnull=False, away_score__isnull=False, status='finished'):
    if not validate_volleyball_score(match.home_score, match.away_score, match.league):
        invalid_matches.append(match)

print(f"Se encontraron {len(invalid_matches)} partidos con resultados inválidos")

# Corregir marcándolos como programados
if input("¿Corregir? (y/N): ").lower() == 'y':
    with transaction.atomic():
        for match in invalid_matches:
            match.home_score = None
            match.away_score = None
            match.status = 'scheduled'
            match.save()
        print(f"Se corrigieron {len(invalid_matches)} partidos")
```

## Scraping de Clubes (NUEVO)

### Importación Inicial de Clubes

```bash
# Scraping completo de todos los clubes desde voleibolib.net
docker-compose exec web python manage.py scrape_clubs --verbose

# Modo dry-run para ver qué se haría sin hacer cambios
docker-compose exec web python manage.py scrape_clubs --dry-run --verbose

# Con delay personalizado entre requests (recomendado para ser respetuoso)
docker-compose exec web python manage.py scrape_clubs --delay 2.0 --verbose
```

### Matching Automático de Equipos con Clubes

```bash
# Solo ejecutar matching de equipos existentes con clubes
docker-compose exec web python manage.py scrape_clubs --match-teams --verbose

# Scraping de clubes + matching en una sola operación
docker-compose exec web python manage.py scrape_clubs --match-teams --verbose
```

### Funcionalidades del Sistema de Clubes

#### **Datos Completos de Clubes**
- Nombre oficial del club
- Presidente/representante
- Datos de contacto (email, teléfono, dirección)
- Información del campo de juego
- Redes sociales (Instagram, Facebook, Twitter, web)
- Logo oficial automático desde federación

#### **Matching Inteligente**
El sistema asocia automáticamente equipos con patrocinadores a sus clubes oficiales:

- `ALARO VOLEI CLINICA DENTAL` → `ALARO VOLEI CLUB ESPORTIU`
- `CAIXA COLONYA CV MANACOR` → `CLUB VOLEIBOL MANACOR`
- `CV SANT JOSEP` → `CLUB ESPORTIU SANT JOSEP OBRER`

#### **Algoritmo de Matching**
1. **Normalización**: Quita acentos, convierte a mayúsculas, elimina caracteres especiales
2. **Similitud**: Usa difflib.SequenceMatcher para calcular similitud
3. **Palabras clave**: Detecta coincidencias parciales significativas
4. **Umbral**: Solo matches con confianza > 0.55 se aplican automáticamente
5. **Manual**: Matches con menor confianza se reportan para revisión

#### **Gestión desde Admin**
- Vista previa de logos en listados
- Acción para sincronizar clubes seleccionados
- Matching manual desde la vista de equipos
- Autocomplete para relación Club-Team
- Campos organizados por categorías (Básico, Contacto, Sede, Redes)

## Ejecución de Scraping

### Scraping de Múltiples Ligas

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

# Scraping de clubes semanal (domingos a las 2:00 AM)
0 2 * * 0 cd /path/to/project && docker-compose exec -T web python manage.py scrape_clubs --match-teams

# O scraping individual por liga
0 20 * * * cd /path/to/project && docker-compose exec -T web python manage.py scrape_league --league-id 7998
```

O configurar Celery para tareas programadas (opcional).

## Estructura de URLs de la Federación

### Patrones Comunes

- **Clasificaciones**: `JSON/get_clasificacion.asp?id={league_id}`
- **Resultados**: `JSON/get_resultados.asp?id={league_id}&f={round}`
- **Calendario**: Similar a resultados pero con partidos futuros
- **Lista de Clubes**: `JSON/get_clubes.asp`
- **Datos de Club**: `JSON/get_datos_club.asp?id={club_id}`
- **Logos de Clubes**: `https://voleibolib.federatio.com/fichas/clubes/{club_id}.jpg`

### Parámetros Dinámicos

- `{league_id}`: ID de la federación de la liga
- `{club_id}`: ID de la federación del club
- `{round}`: Número de jornada (opcional)
- Parámetros adicionales se pueden configurar en `extra_params` (JSON)

## Gestión de Equipos y Clubes

### Relación Club-Team

El nuevo sistema establece una relación clara entre clubes oficiales y equipos:

- **Club**: Entidad oficial con datos de contacto y ubicación
- **Team**: Equipo específico que puede incluir patrocinadores
- **Relación**: Un club puede tener múltiples equipos (senior, cadete, infantil, etc.)

### Normalización de Nombres

El sistema maneja automáticamente:
- Caracteres especiales y acentos (ó → o, à → a)
- Espacios extra
- Diferencias de mayúsculas/minúsculas
- Variaciones menores en nombres
- Eliminación de patrocinadores para matching

### Búsqueda Inteligente

Para equipos de ligas:
1. Busca por nombre normalizado
2. Busca por similitud parcial
3. Registra warnings para revisión manual

Para matching Club-Team:
1. Normaliza nombres de ambos
2. Calcula similitud usando difflib
3. Considera coincidencias de palabras clave
4. Aplica umbral de confianza (0.55)
5. Reporta matches potenciales para revisión manual

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
        'ilovevoley.videos.scraping': {
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

**"Error obteniendo detalles del club"**
- Verificar conectividad a voleibolib.net
- Comprobar que el ID del club existe
- Revisar rate limiting (aumentar delay si es necesario)

**"Matching no encuentra clubes obvios"**
- Revisar umbral de confianza en comando (ajustar --threshold si disponible)
- Verificar normalización de nombres en logs verbose
- Hacer matching manual desde Django admin

### Debugging

```bash
# Scraping con logs detallados
docker-compose exec web python manage.py scrape_league --league-id 7998 --verbose

# Debug de clubes en modo dry-run
docker-compose exec web python manage.py scrape_clubs --dry-run --verbose

# Verificar contenido de endpoint
curl "https://www.voleibolib.net/JSON/get_clasificacion.asp?id=7998"
curl "https://www.voleibolib.net/JSON/get_clubes.asp"
curl "https://www.voleibolib.net/JSON/get_datos_club.asp?id=1"

# Verificar matching desde Django shell
docker compose -f docker-compose.dev.yml run --rm web python manage.py shell
>>> from ilovevoley.teams.models import Team, Club
>>> # Ver equipos sin club
>>> Team.objects.filter(club__isnull=True)
>>> # Ver clubes disponibles
>>> Club.objects.all()
```

## Mantenimiento

### Actualización de Datos

- El scraping actualiza datos existentes sin duplicar
- Las clasificaciones se reemplazan completamente
- Los partidos se actualizan o crean según `federation_id`
- Los clubes se actualizan automáticamente (mantiene relaciones existentes)
- El matching de equipos respeta asociaciones manuales existentes

### Limpieza de Datos

```bash
# Eliminar liga y todos sus datos relacionados
# (Cuidado: esto borra todo)
docker compose -f docker-compose.dev.yml run --rm web python manage.py shell
>>> from ilovevoley.competitions.models import League
>>> from ilovevoley.teams.models import Club
>>> League.objects.get(federation_id='7998').delete()

# Eliminar todos los clubes (mantiene equipos)
>>> Club.objects.all().delete()

# Resetear asociaciones Club-Team
>>> from ilovevoley.teams.models import Team
>>> Team.objects.update(club=None, sponsor_name='')
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

## Ejemplo Completo: Club Multi-Categoría con Sistema de Clubes

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

# 4. Importar todos los clubes con matching automático
docker-compose exec web python manage.py scrape_clubs --match-teams --verbose

# 5. Verificar datos en admin: http://localhost:8000/admin/
# - Ver clubes en /admin/videos/club/
# - Ver equipos asociados en /admin/videos/team/
# - Logos automáticos desde federación

# 6. Programar scraping automático
# Ligas diarias
0 22 * * * cd /path/to/project && docker-compose exec -T web python manage.py scrape_all_leagues
# Clubes semanales
0 2 * * 0 cd /path/to/project && docker-compose exec -T web python manage.py scrape_clubs --match-teams

# 7. Scraping por categorías específicas
docker-compose exec web python manage.py scrape_all_leagues --category "Senior"
```

### **Resultado:**
- **Videos de Senior**: Solo muestran partidos de senior de SANT JOSEP
- **Videos de Cadete**: Solo muestran partidos de cadete de SANT JOSEP  
- **Admin completo**: Ve todos los partidos para gestión integral
- **Datos de clubes**: Información completa de contacto, ubicación y logos automáticos
- **Matching inteligente**: Equipos con patrocinadores asociados automáticamente a clubes oficiales
- **Gestión unificada**: Vista consolidada de toda la información del club y sus equipos

## Descubrimiento automático de ligas (#377)

La federación publica las competiciones de forma escalonada durante todo el año
(categorías que llegan semanas tarde, fases Oro/Plata, copas y campeonatos). El
menú `JSON/get_Menu_Competiciones.asp?temp=2627` tiene tres niveles: sección
(AUTONÓMICA, INSULAR ESCOLAR MALLORCA…) → categoría → fase con enlace
`clasificaciones?id={federation_id}`.

**Flujo:** la tarea `discover_leagues` (`config/celery_schedule.py`, diaria 07:45)
o `manage.py discover_leagues [--season 2026-27]` recorre el menú y, para cada
`federation_id` desconocido, pide la clasificación. Si juega algún equipo de un
tenant crea un `LeagueCandidate` pendiente. Un superuser las valida en el admin
(*Ligas candidatas* → Aprobar / Rechazar). Aprobar crea la `League`; su signal
añade los 3 endpoints de scraping. No toca `League` hasta que se aprueba.

**Qué se propone:** solo ligas con un equipo de un tenant. La clasificación solo
trae nombres, así que se cruza con `Organization.club_team_names` (subcadena,
sin fallback de settings ni matching difuso, #380). Un grupo sin equipos aún se
reintenta en la siguiente pasada, igual que una clasificación que falle por red. Las rechazadas no se vuelven a proponer, y una clasificación con equipos pero ninguno de un tenant se guarda como rechazada (sin equipos coincidentes) para no pedirla cada día; si un tenant cambia sus `club_team_names` hay que reabrirla a mano.

**Categoría:** se detecta por palabra de categoría (alevín, infantil, cadete,
juvenil…) y género claros en la etiqueta. Las ambiguas (`Categoria unificada`,
`ALEVIN` sin género) entran sin categoría y se asigna al aprobar.

**Fases y copas:** la federación no es consistente (a veces otra sección con la
misma categoría, a veces cuelga de la liga existente). Se sugiere como
`parent_league` la liga de la misma temporada y categoría, en cualquier sección;
el superuser la confirma, cambia o vacía. Las ligas dadas de alta a mano que aparecen en el menú (mismo `federation_id`) se enlazan solas con una candidata `approved`, así que también valen como padre. Si sección o fase contienen
"copa", "campeonato" o "torneo" se crea con `competition_type='cup'`.

## Notas Importantes

- ⚠️ **Respetar rate limiting**: No hacer requests muy frecuentes (usar --delay)
- 📊 **Verificar datos**: Revisar logs para detectar problemas
- 🔄 **Backup regular**: Los datos se actualizan automáticamente
- 🆕 **Nuevas fases**: Configurar endpoints adicionales cuando aparezcan liguillas
- 📱 **Monitoreo**: Verificar que las URLs de federación no cambien
- 🏆 **Clubes actualizados**: El sistema mantiene automáticamente los datos de clubes actualizados
- 🎯 **Matching inteligente**: Revisa manualmente los matches sugeridos en logs
- 🔗 **Relaciones preservadas**: Las asociaciones manuales Club-Team no se sobrescriben

## Soporte

Para problemas o nuevas funcionalidades:
1. Revisar logs de scraping
2. Verificar configuración de endpoints
3. Comprobar estructura HTML de la federación
4. Consultar este documento para configuración avanzada