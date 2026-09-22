# Tareas Periódicas con Celery Beat

Este documento explica cómo configurar y usar las tareas periódicas de scraping automático usando django-celery-beat.

## Índice

1. [Introducción](#introducción)
2. [Configuración inicial](#configuración-inicial)
3. [Tareas disponibles](#tareas-disponibles)
4. [Configurar tareas desde el admin](#configurar-tareas-desde-el-admin)
5. [Ejemplos de configuración](#ejemplos-de-configuración)
6. [Monitorización](#monitorización)
7. [Troubleshooting](#troubleshooting)

## Introducción

Las tareas periódicas permiten ejecutar automáticamente las funciones de scraping sin necesidad de ejecutar manualmente los comandos de Django. Esto se hace mediante:

- **Celery**: Sistema de cola de tareas distribuido
- **django-celery-beat**: Programador de tareas periódicas integrado con el admin de Django
- **Redis**: Backend de mensajería y almacenamiento de resultados

## Configuración inicial

### 1. Servicios requeridos

Asegúrate de que los siguientes servicios estén corriendo en Docker:

```bash
# Verificar servicios activos
docker compose -f docker-compose.dev.yml ps

# Deberías ver:
# - db (PostgreSQL)
# - redis
# - web (Django)
# - celery (worker de Celery)
# - celery-beat (programador de tareas)
```

### 2. Migraciones

Las migraciones ya han sido aplicadas, pero si necesitas volver a ejecutarlas:

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate django_celery_beat
```

### 3. Acceder al admin

1. Accede al admin de Django: `http://localhost:8000/admin/`
2. En el menú lateral, busca la sección **"Django Celery Beat"**
3. Encontrarás las siguientes opciones:
   - **Crontabs**: Programación tipo cron (horarios específicos)
   - **Intervals**: Programación por intervalos (cada X tiempo)
   - **Periodic tasks**: Tareas periódicas (aquí configurarás tus tareas)

## Tareas disponibles

### 1. scrape_all_leagues

Ejecuta scraping de todas las ligas activas.

**Nombre de tarea**: `scrape_all_leagues`

**Parámetros opcionales (kwargs)**:
```json
{
    "round_number": 1,
    "category_filter": "senior",
    "delay": 2.0
}
```

- `round_number`: Jornada específica a scrapear (por defecto: None)
- `category_filter`: Filtrar solo ligas de una categoría específica (por defecto: None)
- `delay`: Tiempo de espera entre ligas en segundos (por defecto: 2.0)

**Ejemplo de kwargs**:
```json
{
    "category_filter": "senior",
    "delay": 3.0
}
```

### 2. scrape_league

Ejecuta scraping de una liga específica.

**Nombre de tarea**: `scrape_league`

**Parámetros requeridos (kwargs)**:
```json
{
    "league_id": "ID_DE_LA_LIGA",
    "round_number": 1
}
```

- `league_id`: ID de la federación de la liga (requerido)
- `round_number`: Jornada específica (opcional)

**Ejemplo de kwargs**:
```json
{
    "league_id": "12345",
    "round_number": 5
}
```

### 3. scrape_clubs

Ejecuta scraping de clubes desde voleibolib.net y asocia equipos automáticamente.

**Nombre de tarea**: `scrape_clubs`

**Parámetros opcionales (kwargs)**:
```json
{
    "match_teams": true,
    "delay": 1.0
}
```

- `match_teams`: Si es true, ejecuta matching automático de equipos con clubes (por defecto: true)
- `delay`: Delay entre requests en segundos (por defecto: 1.0)

## Configurar tareas desde el admin

### Opción 1: Usar Intervals (cada X tiempo)

1. **Crear un intervalo**:
   - Ir a **Django Celery Beat > Intervals > Add Interval**
   - Configurar, por ejemplo:
     - Every: `1`
     - Period: `days` (para ejecutar cada día)
   - Guardar

2. **Crear la tarea periódica**:
   - Ir a **Django Celery Beat > Periodic tasks > Add Periodic task**
   - Configurar:
     - **Name**: `Scraping diario de todas las ligas`
     - **Task (registered)**: `scrape_all_leagues`
     - **Enabled**: ✓ (marcar)
     - **Interval**: Seleccionar el intervalo creado
     - **Arguments (kwargs)**: 
       ```json
       {"delay": 2.0}
       ```
   - Guardar

### Opción 2: Usar Crontab (horarios específicos)

1. **Crear un crontab**:
   - Ir a **Django Celery Beat > Crontabs > Add Crontab**
   - Configurar, por ejemplo, para ejecutar todos los días a las 2:00 AM:
     - Minute: `0`
     - Hour: `2`
     - Day of week: `*`
     - Day of month: `*`
     - Month of year: `*`
     - Timezone: `UTC`
   - Guardar

2. **Crear la tarea periódica**:
   - Ir a **Django Celery Beat > Periodic tasks > Add Periodic task**
   - Configurar:
     - **Name**: `Scraping nocturno de todas las ligas`
     - **Task (registered)**: `scrape_all_leagues`
     - **Enabled**: ✓ (marcar)
     - **Crontab**: Seleccionar el crontab creado
     - **Arguments (kwargs)**: 
       ```json
       {"delay": 2.0, "category_filter": "senior"}
       ```
   - Guardar

## Ejemplos de configuración

### Ejemplo 1: Scraping diario completo

**Objetivo**: Scrapear todas las ligas activas cada día a las 3:00 AM

**Configuración**:
- Crear Crontab: `0 3 * * *` (hora 3, todos los días)
- Crear Periodic Task:
  - Name: `Scraping diario completo`
  - Task: `scrape_all_leagues`
  - Crontab: (seleccionar el creado)
  - Kwargs: `{"delay": 2.0}`
  - Enabled: ✓

### Ejemplo 2: Scraping por categoría cada 6 horas

**Objetivo**: Scrapear solo ligas senior cada 6 horas

**Configuración**:
- Crear Interval: Every `6` hours
- Crear Periodic Task:
  - Name: `Scraping senior cada 6h`
  - Task: `scrape_all_leagues`
  - Interval: (seleccionar el creado)
  - Kwargs: `{"category_filter": "senior", "delay": 1.5}`
  - Enabled: ✓

### Ejemplo 3: Actualización de clubes semanal

**Objetivo**: Actualizar base de datos de clubes cada domingo a las 1:00 AM

**Configuración**:
- Crear Crontab: `0 1 * * 0` (hora 1, domingo)
- Crear Periodic Task:
  - Name: `Actualización clubes semanal`
  - Task: `scrape_clubs`
  - Crontab: (seleccionar el creado)
  - Kwargs: `{"match_teams": true, "delay": 1.0}`
  - Enabled: ✓

### Ejemplo 4: Scraping de liga específica cada hora

**Objetivo**: Scrapear una liga específica (por ejemplo, ID 12345) cada hora

**Configuración**:
- Crear Interval: Every `1` hours
- Crear Periodic Task:
  - Name: `Scraping liga principal cada hora`
  - Task: `scrape_league`
  - Interval: (seleccionar el creado)
  - Kwargs: `{"league_id": "12345"}`
  - Enabled: ✓

## Monitorización

### Ver tareas ejecutadas

En el admin, la lista de **Periodic tasks** muestra:
- **Last run at**: Última vez que se ejecutó
- **Total run count**: Número de veces que se ha ejecutado
- Estado (Enabled/Disabled)

### Logs de Celery

Ver logs del worker de Celery:
```bash
docker compose -f docker-compose.dev.yml logs -f celery
```

Ver logs del beat scheduler:
```bash
docker compose -f docker-compose.dev.yml logs -f celery-beat
```

### Ejecutar tarea manualmente

Desde el admin, puedes ejecutar tareas inmediatamente:
1. Ir a la lista de **Periodic tasks**
2. Seleccionar la(s) tarea(s) que quieres ejecutar
3. En "Action", seleccionar **"Ejecutar tareas ahora"**
4. Hacer clic en "Go"

La tarea se enviará a la cola de Celery y se ejecutará inmediatamente.

### Notificaciones por email

Si hay errores durante el scraping automático y tienes las notificaciones por email habilitadas en el `.env`:

```bash
NOTIFICATION_EMAIL_ENABLED=True
ADMIN_EMAIL_LIST=admin@example.com,otro@example.com
```

Recibirás un email con el resumen de errores.

## Troubleshooting

### Las tareas no se ejecutan

1. **Verificar que celery-beat está corriendo**:
   ```bash
   docker compose -f docker-compose.dev.yml ps celery-beat
   ```

2. **Verificar que el worker de Celery está corriendo**:
   ```bash
   docker compose -f docker-compose.dev.yml ps celery
   ```

3. **Reiniciar servicios**:
   ```bash
   docker compose -f docker-compose.dev.yml restart celery celery-beat
   ```

### Error al ejecutar tarea manualmente

Si al ejecutar una tarea manualmente desde el admin obtienes un error de "Tarea no reconocida", verifica:

1. Que el nombre de la tarea en el campo **Task (registered)** sea exactamente:
   - `scrape_all_leagues`
   - `scrape_league`
   - `scrape_clubs`

2. Que el worker de Celery tenga acceso al archivo `tasks.py`

3. Reiniciar el worker de Celery:
   ```bash
   docker compose -f docker-compose.dev.yml restart celery
   ```

### Error de formato JSON en kwargs

Los kwargs deben ser JSON válido. Ejemplos correctos:

✅ Correcto:
```json
{"delay": 2.0}
```

✅ Correcto:
```json
{"category_filter": "senior", "delay": 2.0}
```

❌ Incorrecto (comillas simples):
```json
{'delay': 2.0}
```

❌ Incorrecto (sin comillas en strings):
```json
{category_filter: senior}
```

### Ver tareas registradas en Celery

Para verificar que las tareas están registradas correctamente:

```bash
docker compose -f docker-compose.dev.yml run --rm web python -c "from config.celery import app; print(app.tasks.keys())"
```

Deberías ver las tareas registradas, incluyendo `scrape_all_leagues`, `scrape_league` y `scrape_clubs`.

## Desactivar temporalmente una tarea

Si necesitas desactivar temporalmente una tarea sin eliminarla:

1. Ir a la lista de **Periodic tasks**
2. Hacer clic en la tarea
3. Desmarcar **Enabled**
4. Guardar

La tarea dejará de ejecutarse pero mantendrá su configuración.

## Eliminar una tarea

Para eliminar completamente una tarea periódica:

1. Ir a la lista de **Periodic tasks**
2. Marcar la(s) tarea(s) a eliminar
3. En "Action", seleccionar **"Delete selected periodic tasks"**
4. Confirmar

---

## Comandos útiles

```bash
# Ver logs en tiempo real
docker compose -f docker-compose.dev.yml logs -f celery celery-beat

# Reiniciar servicios de Celery
docker compose -f docker-compose.dev.yml restart celery celery-beat

# Ejecutar comando de scraping manual (alternativa)
docker compose -f docker-compose.dev.yml run --rm web python manage.py scrape_all_leagues --verbose

# Verificar estado de servicios
docker compose -f docker-compose.dev.yml ps

# Ver tareas pendientes en Redis
docker compose -f docker-compose.dev.yml exec redis redis-cli -n 0 KEYS "celery*"
```

## Notas importantes

- Las tareas se ejecutan de forma asíncrona en segundo plano
- El scheduler (celery-beat) lee la configuración de la base de datos cada pocos segundos
- Los cambios en el admin de tareas periódicas se aplican automáticamente sin necesidad de reiniciar servicios
- Es recomendable no ejecutar múltiples scrapers de la misma liga simultáneamente para evitar rate limiting
- Usa el parámetro `delay` para controlar el tiempo entre requests y evitar sobrecargar los servidores externos

## Más información

- [Documentación de Celery](https://docs.celeryproject.org/)
- [Documentación de django-celery-beat](https://django-celery-beat.readthedocs.io/)
- [Sintaxis de Crontab](https://crontab.guru/)


