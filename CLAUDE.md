# CLAUDE.md

Proyecto Django de gestión de vídeos, imágenes y competiciones de voleibol,
multi-tenant por organización.

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

## Restricciones

- Django fijado en **6.0.8** hasta que `django-celery-beat` soporte 6.1+.
- Las 16 tareas Celery llevan `name=` explícito. **No quitarlo**: las filas de
  `PeriodicTask` en base de datos dependen de ese nombre, no de la ruta del
  módulo.

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

## Refactor en curso

La app `videos` se está repartiendo en paquetes. Ver
`docs/superpowers/specs/2026-09-16-refactor-models-design.md`.

**No resucitar la rama `origin/refactor_apps`**: sus migraciones creaban tablas
nuevas y vacías y copiaban las filas a mano. Está descartada.
