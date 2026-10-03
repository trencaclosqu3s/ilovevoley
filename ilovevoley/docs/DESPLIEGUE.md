# 🚀 Guía de Despliegue y CI/CD

Documentación del flujo de integración y despliegue continuo (CI/CD) y operación en producción para I Love Voley.

---

## 1. Despliegue Automático (CI/CD)

El proyecto cuenta con un pipeline automatizado en **GitHub Actions** (`.github/workflows/ci-cd.yml`).

### Flujo de Ejecución:
1. **Pull Requests y Ramas**: En cada push o PR, GitHub Actions ejecuta automáticamente el job **`test`** (`python manage.py check`, comprobación de migraciones pendientes y `pytest`).
2. **Merge en `main`**:
   - Se ejecutan los tests automatizados.
   - Si y **solo si** los tests pasan con éxito, se dispara el job **`deploy`**.
   - El runner de GitHub se conecta al servidor de producción vía SSH y ejecuta `./deploy.sh`.
   - Se compilan las imágenes, se ejecutan migraciones y `collectstatic`, se recrean los servicios con mínimo downtime y se verifica `/healthz` con rollback automático si algo falla.

> [!CAUTION]
> **No ejecutar `docker-compose.dev.yml` en producción**: En el servidor de producción la aplicación corre como proyecto compose `videosvoley` y el compose de desarrollo resuelve al mismo nombre, reutilizando los contenedores `db` y `redis` de producción y pudiendo causar colisiones o corrupción de datos.

---

## 2. Configuración de Secretos y Variables de Entorno

### Secretos en GitHub Actions (`Settings` > `Secrets and variables` > `Actions`):

| Secreto | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `SSH_HOST` | IP o dominio público del servidor VPS | `vps.tudominio.es` o `123.45.67.89` |
| `SSH_USER` | Usuario en el servidor con permisos Docker | `deploy` |
| `SSH_KEY` | Clave privada SSH (sin passphrase) | Contenido de `~/.ssh/id_ed25519` |
| `SSH_PORT` | Puerto SSH del servidor (opcional) | `22` (por defecto) |
| `DEPLOY_PATH` | Ruta absoluta al repositorio en el servidor | `/opt/videosvoley` |

### Variables de Entorno Requeridas en Producción (`.env`):
- **Base de Datos**: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
- **Seguridad**: `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
- **Dominio Multi-Tenant**: `SESSION_COOKIE_DOMAIN=.ilovevoley.es`, `CSRF_COOKIE_DOMAIN=.ilovevoley.es`, `TENANT_BASE_DOMAIN=ilovevoley.es`.
- **Web Push (VAPID)**:
  - `VAPID_PUBLIC_KEY`: Clave pública RFC 8292.
  - `VAPID_PRIVATE_KEY`: Clave privada.
  - `VAPID_CLAIMS_SUB`: Contacto (ej. `mailto:admin@ilovevoley.es`).
  - *(Generables con: `docker compose run --rm web python manage.py generate_vapid_keys`)*.
- **Sentry**: `SENTRY_DSN`, `SENTRY_ENVIRONMENT=production`.

---

## 3. Despliegue Manual y Funcionamiento de `./deploy.sh`

Para desplegar manualmente en el servidor:

```bash
cd /opt/videosvoley
./deploy.sh
```

### ¿Qué hace exactamente `./deploy.sh`?
1. **Guarda el estado previo**: Registra `PREV_COMMIT` para permitir rollback en caso de error.
2. **Descarga código**: `git pull`.
3. **Release Tracking**: Exporta `GIT_SHA` para que Sentry asocie los errores a la versión desplegada.
4. **Construcción de Imágenes**: `docker compose build`. El Dockerfile compila automáticamente las traducciones (`compilemessages`).
5. **Migraciones**: `docker compose run --rm web python manage.py migrate` (si falla, ejecuta rollback).
6. **Archivos Estáticos**: `docker compose run --rm web python manage.py collectstatic --noinput` (sin `--clear`, evitando ventanas de 404 durante el despliegue).
7. **Recreación de Contenedores**: `docker compose up -d --remove-orphans`.
8. **Recarga de Nginx**: Comprueba `nginx -t` y recarga la configuración (`nginx -s reload` o recreación segura).
9. **Healthcheck y Rollback**: Comprueba el endpoint `/healthz` en hasta 10 intentos. Si el contenedor no responde saludablemente, revierte el código a `PREV_COMMIT`, recompila y restaura los servicios.

> [!NOTE]
> **El papel de `entrypoint.sh` (#118)**: El script `entrypoint.sh` **ya no ejecuta migraciones ni `collectstatic`**. Su única responsabilidad es esperar a que PostgreSQL esté disponible (`pg_isready`) y ejecutar el comando solicitado (`exec "$@"`).

---

## 4. Traducciones e Internacionalización (`i18n`)

El proyecto soporta castellano (`es`) y catalán (`ca`). Los archivos `.mo` compilados están ignorados en git.
- Durante el build de Docker (`docker compose build`), el comando `compilemessages` se ejecuta automáticamente en la imagen.
- Si en desarrollo o en el servidor se modifican los archivos `.po` sin reconstruir la imagen Docker:
  ```bash
  docker compose run --rm web python manage.py compilemessages
  ```

---

## 5. Comandos Útiles de Operación

### Ver logs en tiempo real:
```bash
docker compose logs -f web
docker compose logs -f celery
```

### Reiniciar un servicio individual:
```bash
docker compose restart web
docker compose restart nginx
```

### Ejecutar un comando Django puntual:
```bash
docker compose run --rm web python manage.py <comando>
```
