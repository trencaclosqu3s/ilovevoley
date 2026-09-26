# AGENTS.md

Proyecto Django de gestión de vídeos, imágenes, competiciones y plantillas de
voleibol, multi-tenant por organización.

## Arquitectura y apps (`ilovevoley.*`)

El paquete raíz es `ilovevoley`. La lógica se divide en apps de dominio:

- **`core`**: Multi-tenant (`Organization`, con subdominios via `TenantMiddleware`,
  `club` federativo vinculado y `default_home` configurable), modelo centralizado
  de temporadas (`Season` con temporada activa única `is_current`, helpers de
  normalización `YYYY-YY` y corte el 1 de septiembre), `Category`, auditoría y
  panel de moderación descentralizada (`/core/moderacion/`).
- **`competitions`**: Ligas (`League`, con FK a `Season` y M2M `categories`),
  partidos (`Match`), clasificaciones (`Standing`), endpoints de scraping
  (`ScrapingEndpoint`), parsers federativos (voleibolib / RFEVB) y suscripción
  ICS a calendario.
- **`teams`**: Clubes oficiales (`Club`), equipos (`Team`) y variantes de equipo
  (`parent_team`, `variant_type` para equipos filiales/colores).
- **`rosters`**: Plantillas históricas (`Person`, `PlayerRole`, `StaffRole`)
  vinculadas a `Season`, con constraints de dorsal y rol por temporada, y
  soporte multi-rol para cuerpo técnico.
- **`content`**: Vídeos (`Video`), imágenes (`Image`), comentarios (`Comment`),
  álbumes grupales (`album_group_id`), etiquetado automático y moderación con
  Google Vision API, vinculados a `Season` y filtrados por temporada activa.
- **`users`**: Modelo `User` personalizado, membresías por club (`Membership` con
  roles `admin`, `manager`, `member`), autenticación Google OAuth (solo para
  identificar al usuario, sin tokens: `SOCIALACCOUNT_STORE_TOKENS = False`) y
  suscripción de partidos por feed iCal (`calendar_token`), no por la API de
  Google Calendar.
- **`videos`**: Paquete legado que se mantiene **exclusivamente** como capa de
  compatibilidad para URLs antiguas y las tareas periódicas Celery. Nuevos modelos
  o vistas deben ir a su app de dominio correspondiente.

## Comandos

Todo comando Django se ejecuta dentro de Docker:

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py <comando>
```

Tests:

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```

`--create-db` es **obligatorio**: sin él la BD de test queda desactualizada y
fallan columnas inexistentes.

**No ejecutar `docker-compose.dev.yml` en el servidor de producción.** Allí la
aplicación corre como proyecto compose `videosvoley` y el compose de desarrollo
resuelve al mismo nombre, así que reutilizaría los contenedores `db` y `redis`
de producción. Para una consulta puntual en producción se usa el compose por
defecto: `docker compose run --rm web python manage.py <comando>`.

## Restricciones y Reglas de Negocio

- **Django fijado en 6.0.8** hasta que `django-celery-beat` soporte 6.1+.
- **Tareas Celery**: Las 16 tareas Celery llevan `name=` explícito. **No quitarlo**:
  las filas de `PeriodicTask` en base de datos dependen de ese nombre, no de la
  ruta del módulo.
- **Managers de Match**: Usar `Match.objects` (excluye automáticamente partidos
  con estado `withdrawn`) o `Match.all_objects` (incluye todos sin filtrar).
- **Validación de resultados**: Validar siempre marcadores de voleibol con
  `validate_volleyball_score(home_score, away_score, league)` antes de marcar un
  partido como finalizado.
- **Temporadas**: Utilizar siempre `Season.objects.current()` para la temporada
  activa y `resolve_season_filter(request)` para la convención de filtros de UI.
- **No resucitar la rama `origin/refactor_apps`**: está completamente descartada.

## Testing

Un test existe solo si protege una decisión propia del producto. No basta con
que suba cobertura.

**Debe existir si**: protege una regla de negocio; cubre un caso límite que ya
falló o sería caro detectar en producción; verifica una transformación de datos
no trivial (parsing, normalización, resolución de duplicados); cubre un flujo
con efectos persistentes; comprueba manejo de errores en un camino crítico
(rollback, idempotencia); documenta una decisión ambigua.

**No debe existir si**: solo comprueba que Django o el ORM hacen lo suyo; solo
valida `status_code` sin comprobar efecto o payload; comprueba HTML decorativo o
clases CSS; duplica otro test más fuerte; mockea tanto que solo verifica el
mock; prueba getters, setters o properties simples.

**Antes de añadir un test**: si falla, ¿qué comportamiento real se habría roto?
¿Obligaría a cambiar código de producto o solo el test? ¿Prueba nuestra lógica o
la de la librería?

**Estructura**: `app_name/tests/` con `__init__.py`, separando `test_models.py`,
`test_views.py`, `test_forms.py`, `test_utils.py`, `test_templatetags.py`,
`test_admin.py` (este último solo si hay lógica propia).

**Admin**: saltar configuración de `ModelAdmin` y CRUD estándar; testear solo
métodos con lógica, `get_queryset()` complejos, acciones custom y `save_model()`
con validación.
