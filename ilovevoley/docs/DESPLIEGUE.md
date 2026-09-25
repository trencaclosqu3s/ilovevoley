# 🚀 Guía de Despliegue y CI/CD

## 1. Despliegue Automático (CI/CD)

El proyecto cuenta con un pipeline automatizado en **GitHub Actions** (`.github/workflows/ci-cd.yml`).

### ¿Cómo funciona?
1. Creas una rama o Pull Request con tus cambios.
2. En cada push o PR, GitHub Actions ejecuta automáticamente el job **`test`** (`python manage.py check`, comprobación de migraciones pendientes y `pytest`).
3. Al hacer merge o push a la rama **`main`**:
   - Se ejecutan los tests.
   - Si y **solo si** los tests pasan con éxito, se dispara el job **`deploy`**.
   - El runner de GitHub se conecta al servidor de producción vía SSH y ejecuta `./deploy.sh`.
   - Se compilan imágenes y se recrean los servicios con mínimo downtime (`docker compose up -d --remove-orphans`).
   - `entrypoint.sh` se encarga automáticamente de aplicar migraciones pendientes y ejecutar `collectstatic`.

---

## 2. Configuración de Secretos en GitHub

Para que el job de despliegue pueda conectar con el servidor, deben configurarse los siguientes secretos en el repositorio en GitHub (`Settings` > `Secrets and variables` > `Actions` > `Repository secrets`):

| Secreto | Descripción | Ejemplo |
| :--- | :--- | :--- |
| `SSH_HOST` | IP o dominio público del servidor VPS | `vps.tudominio.es` o `123.45.67.89` |
| `SSH_USER` | Usuario en el servidor con permisos Docker | `root` o `deploy` |
| `SSH_KEY` | Clave privada SSH (sin passphrase) | Contenido de `~/.ssh/id_ed25519` |
| `SSH_PORT` | Puerto SSH del servidor (opcional) | `22` (por defecto) |
| `DEPLOY_PATH` | Ruta absoluta al repositorio en el servidor | `/opt/videosvoley` |

### Cómo generar la clave SSH para GitHub Actions (si es necesario)
En tu máquina o en el servidor:
```bash
# 1. Generar par de claves dedicado sin contraseña
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_deploy

# 2. En el servidor, añadir la clave pública a authorized_keys
cat ~/.ssh/github_actions_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# 3. Copiar el contenido de la clave privada (~/.ssh/github_actions_deploy) en el secreto SSH_KEY de GitHub
cat ~/.ssh/github_actions_deploy
```

---

## 3. Despliegue Manual (Contingencia)

Si en algún momento necesitas desplegar manualmente directamente en el servidor sin pasar por GitHub Actions:

```bash
cd /opt/videosvoley  # o tu ruta de despliegue
./deploy.sh
```

### ¿Qué hace `./deploy.sh`?
1. `git pull` para descargar los últimos cambios de `main`.
2. Exporta `GIT_SHA` para el release tracking en Sentry.
3. `docker compose build` para compilar cambios en Dockerfile o dependencias.
4. `docker compose up -d --remove-orphans` para recrear solo los contenedores afectados con mínimo downtime.
5. `entrypoint.sh` ejecuta automáticamente:
   - Espera a que la base de datos esté lista.
   - `python manage.py migrate --noinput`.
   - `python manage.py collectstatic --noinput --clear`.
   - Arranque de servicios (`web`, `celery`, `celery-beat`).

---

## 4. Comandos útiles en el servidor

### Ver logs en tiempo real
```bash
docker compose logs -f web
```

### Reiniciar solo el servidor web
```bash
docker compose restart web
```

### Reconstruir todo desde cero
```bash
docker compose down
docker compose build
docker compose up -d
```

### Limpiar archivos estáticos (si hay problemas)
```bash
sudo rm -rf /opt/videosvoley/static/*
./deploy.sh
```

---

## 5. Estructura de archivos estáticos

- `ilovevoley/static/` - **Código fuente** (se sube a git)
- `/opt/videosvoley/static/` - **Archivos recopilados** en producción (volumen Docker)
- `staticfiles/` - Archivos recopilados locales (ignorado por git)

Para más detalles sobre la gestión de estáticos, consulta `SOLUCION_STATIC.md`.
