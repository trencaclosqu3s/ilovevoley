# CHANGELOG - Tareas Periódicas con Celery Beat

## Resumen de cambios

Se ha implementado un sistema completo de tareas periódicas usando django-celery-beat que permite configurar y ejecutar automáticamente las tareas de scraping desde el admin de Django.

## Fecha
8 de octubre de 2025

## Archivos nuevos

### 1. `videosvoley/videos/tasks.py`
Archivo nuevo con las tareas de Celery para scraping automático:

- **`scrape_all_leagues_task`**: Scrapea todas las ligas activas con opciones de filtrado por categoría
- **`scrape_league_task`**: Scrapea una liga específica
- **`scrape_clubs_task`**: Scrapea clubes desde voleibolib.net con matching automático de equipos

Características:
- Logging detallado de cada operación
- Notificaciones por email a administradores en caso de errores (si está habilitado)
- Gestión de errores robusto con reportes detallados
- Parámetros configurables para cada tarea

### 2. `videosvoley/docs/TAREAS_PERIODICAS.md`
Documentación completa sobre cómo usar el sistema de tareas periódicas:

- Configuración inicial
- Explicación de todas las tareas disponibles
- Ejemplos de configuración con Intervals y Crontabs
- Casos de uso comunes
- Troubleshooting
- Comandos útiles

## Archivos modificados

### 1. `config/settings.py`
**Cambio**: Agregado `django_celery_beat` a `INSTALLED_APPS`

```python
INSTALLED_APPS = [
    # ...
    'django_celery_beat',  # Para gestionar tareas periódicas desde el admin
    # ...
]
```

### 2. `videosvoley/videos/admin.py`
**Cambios**: Agregada configuración personalizada del admin para Celery Beat

- Import de modelos de django-celery-beat: `PeriodicTask`, `IntervalSchedule`, `CrontabSchedule`
- Clase `CustomPeriodicTaskAdmin` con:
  - Lista de campos personalizados mostrando información relevante
  - Filtros y búsqueda
  - Acciones personalizadas:
    - `enable_tasks`: Habilitar tareas seleccionadas
    - `disable_tasks`: Deshabilitar tareas seleccionadas
    - `run_tasks_now`: Ejecutar tareas inmediatamente
  - Descripción de ayuda en fieldsets para facilitar la configuración
  - Manejo inteligente de argumentos JSON

### 3. `docker-compose.dev.yml`
**Cambios**: Agregados servicios necesarios para Celery

Servicios añadidos:
- **redis**: Servidor Redis para cola de mensajes
- **celery**: Worker de Celery para ejecutar tareas
- **celery-beat**: Scheduler para tareas periódicas con DatabaseScheduler

Actualizaciones:
- Variable de entorno `REDIS_URL` agregada al servicio `web`
- Dependencia de `redis` agregada al servicio `web`

### 4. `docker-compose.yml`
**Cambio**: Actualizado comando de celery-beat

```yaml
command: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Ahora usa el DatabaseScheduler para leer la configuración de tareas desde la base de datos.

## Migraciones

Se ejecutaron las migraciones de django-celery-beat para crear las tablas necesarias:
- `django_celery_beat_crontabschedule`
- `django_celery_beat_intervalschedule`
- `django_celery_beat_periodictask`
- `django_celery_beat_solarschedule`
- `django_celery_beat_clockedschedule`
- `django_celery_beat_periodictasks`

## Cómo usar

### 1. Iniciar servicios
```bash
docker compose -f docker-compose.dev.yml up -d
```

### 2. Acceder al admin
1. Ir a `http://localhost:8000/admin/`
2. Buscar la sección **"Django Celery Beat"**
3. Crear Intervals o Crontabs según necesites
4. Crear Periodic Tasks asociadas a las tareas de scraping

### 3. Tareas disponibles
- `scrape_all_leagues` - Scrapea todas las ligas activas
- `scrape_league` - Scrapea una liga específica
- `scrape_clubs` - Scrapea clubes y asocia equipos

## Ventajas del nuevo sistema

1. **Configuración desde el admin**: No necesitas editar código o archivos de configuración
2. **Flexibilidad**: Puedes crear, modificar, habilitar/deshabilitar tareas fácilmente
3. **Monitorización**: Ver cuándo se ejecutó cada tarea y cuántas veces
4. **Ejecución manual**: Ejecutar tareas inmediatamente desde el admin sin esperar al schedule
5. **No hay downtime**: Los cambios se aplican sin necesidad de reiniciar servicios
6. **Múltiples schedules**: Puedes tener diferentes tareas con diferentes horarios
7. **Notificaciones**: Recibir emails automáticamente si hay errores

## Diferencia con los comandos anteriores

### Antes (manual):
```bash
# Tenías que ejecutar manualmente cada vez
docker compose -f docker-compose.dev.yml run --rm web python manage.py scrape_all_leagues
```

### Ahora (automático):
- Configuras una vez desde el admin
- La tarea se ejecuta automáticamente según el horario configurado
- Puedes ver el historial de ejecuciones
- Recibes notificaciones si hay errores

Los comandos de Django siguen disponibles para uso manual si lo necesitas.

## Ejemplos de configuración

### Scraping diario a las 3 AM
1. Crear Crontab: `0 3 * * *`
2. Crear Periodic Task:
   - Name: "Scraping diario completo"
   - Task: `scrape_all_leagues`
   - Crontab: (seleccionar el creado)
   - Kwargs: `{"delay": 2.0}`
   - Enabled: ✓

### Scraping cada 6 horas
1. Crear Interval: Every `6` hours
2. Crear Periodic Task:
   - Name: "Scraping cada 6h"
   - Task: `scrape_all_leagues`
   - Interval: (seleccionar el creado)
   - Enabled: ✓

## Troubleshooting

### Ver logs
```bash
# Logs de Celery worker
docker compose -f docker-compose.dev.yml logs -f celery

# Logs de Celery beat
docker compose -f docker-compose.dev.yml logs -f celery-beat
```

### Reiniciar servicios
```bash
docker compose -f docker-compose.dev.yml restart celery celery-beat
```

### Verificar tareas registradas
```bash
docker compose -f docker-compose.dev.yml run --rm web python -c "from config.celery import app; print(list(app.tasks.keys()))"
```

## Notas importantes

- Las tareas se ejecutan en background de forma asíncrona
- El scheduler lee la base de datos cada pocos segundos para detectar cambios
- Se recomienda usar el parámetro `delay` para evitar rate limiting en los servidores externos
- Los errores se reportan por email si `NOTIFICATION_EMAIL_ENABLED=True` en el `.env`

## Testing

Para probar que todo funciona:

1. Crear una tarea de prueba con interval de 1 minuto
2. Verificar en los logs que se ejecuta:
   ```bash
   docker compose -f docker-compose.dev.yml logs -f celery
   ```
3. Ver en el admin que `Last run at` y `Total run count` se actualizan

## Próximos pasos sugeridos

- [ ] Configurar las tareas periódicas según tus necesidades
- [ ] Activar notificaciones por email configurando el `.env`
- [ ] Monitorizar los logs durante los primeros días
- [ ] Ajustar los horarios según el volumen de datos

## Más información

Ver documentación completa en: `videosvoley/docs/TAREAS_PERIODICAS.md`

