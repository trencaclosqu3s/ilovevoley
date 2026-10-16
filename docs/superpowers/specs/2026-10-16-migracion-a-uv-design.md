# Migración a uv + pyproject.toml (build, CI y dependencias)

Fecha: 2026-10-16 · Issue: https://github.com/trencaclosqu3s/ilovevoley/issues/558 · Rama: `feature-migracion-a-uv`
Estado: spec aprobada. Implementación pendiente (plan: `docs/superpowers/plans/2026-10-16-migracion-a-uv.md`, local y no versionado).

## Objetivo

Dejar de resolver dependencias con `pip` en cada build y pasar a un lockfile
verificado, sin cambiar el flujo de despliegue (`./deploy.sh` sigue igual).

Dos motivos, por orden de peso:

1. **Reproducibilidad.** Hoy `requirements.txt` fija los transitivos con `==` pero
   **no** los pinea ni usa hashes: `pip wheel` los resuelve en el momento del build.
   Un release transitivo roto o retirado de PyPI puede romper el build de producción
   sin que haya cambiado una línea del repo.
2. **Velocidad de CI.** El workflow instala en cada push con `pip`; `uv` resuelve e
   instala desde el lock en una fracción del tiempo, con caché de intérprete y de
   paquetes.

También se gana: `pip install` en el `runtime` era offline (`--no-index`); con uv
la única etapa con red sigue siendo el builder, que además verifica hashes del lock.

## Decisiones

| Decisión | Elección |
|---|---|
| Fuente de verdad | `pyproject.toml` + `uv.lock`. Se borran `requirements.txt` y `requirements-dev.txt`. |
| Grupos dev/prod | `[dependency-groups]` (PEP 735), grupo `dev`. `uv sync` lo instala por defecto; `--no-dev` lo excluye. |
| Venv en la imagen | `/opt/venv` (fuera de `/app`, para que el bind-mount `.:/app` de `docker-compose.dev.yml` no lo tape). |
| Construcción de imagen | Enfoque A: venv en `builder`, `COPY --from=builder` al `runtime`. El `runtime` no lleva uv ni toolchain. |
| Detección de lock desincronizado | `--locked` (no `--frozen`): falla el build/CI si `pyproject.toml` y `uv.lock` no concuerdan. |
| Dependabot | Ecosistema `uv` + `cooldown: default-days: 7`. |
| Caducidad de releases | `[tool.uv] exclude-newer = "7 days"`. |
| uv local | Sí (`brew install uv`); `.python-version` = `3.13` para que host, CI e imagen coincidan. |
| uv pinneado | `0.13.1` (imagen y CI) y hook `uv-pre-commit` `0.13.1`. |
| `deploy.sh` | Sin cambios. |

## Estado actual

- `requirements.txt`: 24 pines directos, sin transitivos ni hashes.
- `requirements-dev.txt`: `-r requirements.txt` + 5 herramientas (`pytest`, `pytest-django`, `pytest-xdist`, `bandit`, `pip-audit`).
- `Dockerfile`: 4 stages (`builder` con `pip wheel`, `runtime` con `pip install --no-index --find-links=/wheels`, `dev` que añade el grupo dev).
- `.github/workflows/ci-cd.yml`: `actions/setup-python` con `cache: pip`, `pip install -r requirements-dev.txt`, `pip-audit -r requirements.txt`, bandit, `manage.py check`/`check --deploy`/`makemigrations --check`/`compilemessages`, `pytest --create-db -n auto`.
- Referencias a `requirements*.txt` fuera de los propios ficheros: `Dockerfile`, `README.md:114`, `.github/dependabot.yml:40`, `.github/workflows/ci-cd.yml:65,68`, `ilovevoley/docs/IMAGENES.md:48`. (Las specs en `docs/superpowers/specs/` son históricas: no se tocan.)

## Cambios por archivo

### 1. `pyproject.toml` (nuevo)

```toml
[project]
name = "ilovevoley"
version = "0.0.0"
description = "Plataforma de gestión de vídeos, imágenes, competiciones y plantillas de voleibol"
requires-python = ">=3.13,<3.14"
dependencies = [
    "Django==6.0.8",
    "django-unfold==0.108.0",
    "psycopg2-binary==2.9.13",
    "python-decouple==3.8",
    "Pillow==12.3.0",
    "pillow-heif==1.8.1",
    "django-allauth==65.19.7",
    "requests==2.34.2",
    # Requerido por allauth para verificar ID tokens de Google OAuth2
    # (evita el extra [socialaccount] que arrastra oauthlib/CVE-2026-49265)
    "PyJWT==2.15.1",
    "cryptography==50.0.2",
    "unidecode==1.4.0",
    "beautifulsoup4==4.15.0",
    "celery==5.6.3",
    "django-celery-beat==2.9.0",
    "google-cloud-vision==3.16.0",
    "google-auth==2.61.0",
    "django-storages==1.14.6",
    "redis==8.1.0",
    "gunicorn==26.2.0",
    "django-ical==1.9.2",
    "pypdf>=6.20.0",
    "sentry-sdk[django]==2.71.0",
    "django-ratelimit==4.1.0",
    "pywebpush==2.5.0",
]

[dependency-groups]
dev = [
    "pytest==9.1.1",
    "pytest-django==4.14.0",
    "pytest-xdist==3.8.0",
    "bandit==1.9.4",
    "pip-audit==2.10.1",
]

[tool.uv]
# El proyecto no es un paquete instalable: no se buildea ni se instala a sí mismo.
package = false
# Margen frente a releases recién publicadas (acompañado del cooldown de Dependabot).
exclude-newer = "7 days"
```

Los pines se copian literales de `requirements.txt` (incluido `pypdf>=6.20.0`, que
pasa de rango a versión exacta vía `uv.lock`). No se relaja ninguno.
`requires-python` acota a 3.13 igual que la imagen `python:3.13-slim`.

### 2. `.python-version` (nuevo)

```
3.13
```

uv descarga y usa CPython 3.13 en el host aunque el sistema tenga otro.

### 3. `uv.lock` (nuevo, commiteado)

Generado con `uv lock`. Incluye transitivos y hashes.

### 4. `Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1

# Versión de uv pinneada: Dependabot no rastrea los `COPY --from=` de imágenes,
# así que esta referencia se actualiza a mano junto con la de ci-cd.yml.

# --- builder: resuelve el lock e instala el entorno virtual de producción ---
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=python3.13 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libheif-dev \
    libde265-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Solo manifiesto y lock: si cambia el código, esta capa se reutiliza. --locked
# aborta el build si el lock no concuerda con pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# --- runtime: producción, solo el venv desde el builder ---
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# postgresql-client aporta pg_isready para entrypoint.sh, curl para healthcheck.
# gettext aporta msgfmt, necesario para `compilemessages` en el despliegue.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    gettext \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos '' --uid 1000 appuser

# El venv lo construye uv en el builder; el runtime no lleva toolchain ni uv.
# Queda como root y de solo lectura para appuser (basta con o+rx).
COPY --from=builder /opt/venv /opt/venv

# El código pertenece a root: appuser lo lee pero no puede modificarlo.
# Solo media, staticfiles y locale (compilemessages) son escribibles.
COPY . .

# Compilar los catálogos de traducción en build: los .mo son artefactos
# derivados (gitignored) y appuser no puede escribir el locale si el usuario
# que ejecuta el despliegue no coincide con el owner del bind-mount.
RUN SECRET_KEY=build DB_PASSWORD=build python manage.py compilemessages

RUN mkdir -p /app/media /app/staticfiles /app/locale && \
    chown -R appuser:appuser /app/media /app/staticfiles /app/locale

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-"]

# --- dev: último stage para que `build: .` sin target (docker-compose.dev.yml)
# siga teniendo pytest. Producción construye con `target: runtime`.
FROM runtime AS dev

USER root

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=python3.13 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
# Añade el grupo dev (uv sincroniza el grupo `dev` por defecto) sobre el venv de prod.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

USER appuser
```

Desaparecen el stage intermedio de `/wheels` y los tres `pip`.

### 5. `.github/workflows/ci-cd.yml`

Se sustituye `actions/setup-python` por `setup-uv` y todas las invocaciones pasan
por `uv run`. Cambios concretos en el job `test`:

```yaml
      - name: Instalar uv y el intérprete
        uses: astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0
        with:
          version: '0.13.1'
          python-version: '3.13'
          enable-cache: true

      - name: Instalar dependencias del sistema
        run: |
          sudo apt-get update
          sudo apt-get install -y libheif-dev libde265-dev pkg-config gettext

      - name: Instalar dependencias Python
        run: uv sync --locked

      - name: Auditoría de vulnerabilidades en dependencias
        run: |
          uv export --locked --no-dev --no-hashes --format requirements-txt -o /tmp/audit-requirements.txt
          uv run --locked pip-audit -r /tmp/audit-requirements.txt

      - name: Análisis estático de seguridad con Bandit
        run: uv run --locked bandit -r config ilovevoley -x '*/tests/*' -ll

      - name: Comprobaciones de Django
        run: uv run --locked python manage.py check

      - name: Verificación de configuración de despliegue
        env:
          DEBUG: 'False'
          SECRET_KEY: django-ci-deploy-check-secret-key-with-50-characters-and-high-entropy
          ALLOWED_HOSTS: localhost,127.0.0.1
        run: uv run --locked python manage.py check --deploy

      - name: No debe haber migraciones pendientes de generar
        run: uv run --locked python manage.py makemigrations --check --dry-run

      - name: Compilar catálogos de traducción
        run: uv run --locked python manage.py compilemessages

      - name: Tests
        run: uv run --locked pytest --create-db -n auto -v
```

Se mantienen sin tocar el checkout, Gitleaks, el job `deploy` y la política de
pinear las acciones por SHA con comentario de versión. No hace falta un paso
`uv lock --check` aparte: `--locked` en `uv sync`/`uv run` ya falla si el lock no
concuerda con `pyproject.toml` (uv los documenta como equivalentes).

### 6. `.github/dependabot.yml`

El bloque `pip` se sustituye por:

```yaml
  # Update Python dependencies (pyproject.toml / uv.lock)
  - package-ecosystem: 'uv'
    directory: '/'
    schedule:
      interval: 'weekly'
    cooldown:
      default-days: 7
    groups:
      python:
        update-types:
          - 'minor'
          - 'patch'
```

`cooldown` debe coincidir con `exclude-newer`; si no, Dependabot propondría PRs que
uv no puede lockear.

### 7. `.pre-commit-config.yaml`

Se añade un repo remoto para que el lock no se quede atrás al tocar `pyproject.toml`:

```yaml
  - repo: https://github.com/astral-sh/uv-pre-commit
    rev: 0.13.1
    hooks:
      - id: uv-lock
```

### 8. Documentación

- `README.md:114`: en el árbol, `requirements.txt` → `pyproject.toml` + `uv.lock` + `.python-version`.
- `ilovevoley/docs/IMAGENES.md:48`: "incluidas en `pyproject.toml`".
- `AGENTS.md`: nota en «Comandos» sobre dónde viven ahora las dependencias y cómo se añade una (editar `pyproject.toml` → `uv lock`, o `uv add <paquete>`), y que el build instala desde `uv.lock`. Los comandos de Docker documentados no cambian.

### 9. Borrados

`requirements.txt`, `requirements-dev.txt`.

### 10. Sin cambios

- `.dockerignore`: vale tal cual. `.venv` ya está ignorado; `pyproject.toml` y
  `uv.lock` **deben** seguir entrando en el contexto de build (son la entrada de
  `uv sync`), y ningún patrón actual los excluye.
- `docker-compose.yml`, `docker-compose.dev.yml`, `deploy.sh`, `entrypoint.sh`,
  `pytest.ini`: sin cambios. El stage `dev` sigue siendo el último, así que
  `build: .` sin `target` continúa resolviendo a él.

## Cómo se añade o actualiza una dependencia

- Pinear a mano: editar `dependencies` en `pyproject.toml` y `uv lock`.
- Actualizar todo: `uv lock --upgrade`; uno solo: `uv lock --upgrade-package <paquete>`.
- En local (host con uv instalado) o dentro de la imagen de dev
  (`docker compose -f docker-compose.dev.yml run --rm web uv lock`).
- Si `pyproject.toml` cambia sin relockear, CI y build de Docker fallan (`--locked`
  en `uv sync`/`uv run`): es la red de seguridad.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| uv resuelve transitivos distintos que pip y cambia comportamiento | Antes de tocar nada de CI/Docker: `pip freeze` desde la imagen runtime actual y `uv export` del lock nuevo, y revisar el diff. Cualquier salto de versión se aprueba explícitamente. |
| `gunicorn` no encuentra `config.wsgi` con el venv en `/opt/venv` | Hoy el paquete se resuelve por `cwd` (`/app`). Verificar en la imagen final con `gunicorn config.wsgi:application --check-config` antes de dar por bueno el `CMD`. |
| Dependabot no siempre actualiza `uv.lock` al bumpear `pyproject.toml` | `--locked` en CI lo detecta y obliga a relockear en el mismo PR. |
| La versión de uv de `COPY --from=ghcr.io/...` no la rastrea Dependabot | Pinneada a `0.13.1`, documentada, y se actualiza a mano junto con la de CI. |
| `--locked` puede ser más estricto de lo esperado con `exclude-newer` | Verificado: `exclude-newer` solo afecta a la resolución, no marca el lock como desactualizado. |
| `/opt/venv` es root y de solo lectura para `appuser` | Es el comportamiento buscado (prod no debe mutar sus dependencias). Si algún flujo necesita escribir, se verá en la verificación. |
| Índice de PyPI no disponible durante el build | Sin cambio real: el builder ya necesitaba red. El runtime sigue sin tocarla. |

## Pendiente de confirmar durante la implementación

Son comprobaciones, no decisiones abiertas; si alguna falla, la alternativa está al lado:

1. Que `uv sync --locked --no-dev` acepte `--no-dev` (documentado para excluir el
   grupo `dev`; alternativa `--no-group dev`).
2. Que `uv export --locked --no-dev --no-hashes --format requirements-txt` funcione
   con `package = false` (alternativa: quitar `--no-dev` y auditar todo el árbol).
3. Que `pip-audit -r` acepte el export sin `--no-deps`; si re-resuelve de más, añadirlo.
4. Que `pillow-heif==1.8.1` y `psycopg2-binary==2.9.13` tengan wheel para CPython 3.13
   (si no, el builder ya tiene el toolchain y `libheif-dev`).
5. Opcional, no incluido: `UV_MALWARE_CHECK=1` en el builder (chequeo de malware en
   preview al sincronizar). Se decide con el resultado de la verificación.

## Verificación

Sin tests nuevos: es un cambio de toolchain, no de producto. Según
`docs/ai-guidelines/testing-guidelines.md`, no hay regla de negocio que proteger ni
transformación de datos que testear; la verificación es de build y de suite existente.

1. `uv lock` genera el lock; revisar que incluye hashes y que el diff de versiones
   contra `pip freeze` de la imagen actual está justificado.
2. `docker compose build` (target `runtime`) en frío: construcción correcta.
3. `docker compose -f docker-compose.dev.yml build web`: pytest disponible.
4. Dentro de la imagen de dev: `python -m pytest --create-db -n auto` en verde.
5. Dentro de la imagen de runtime: `gunicorn config.wsgi:application --check-config`
   y `python manage.py check --deploy` en verde.
6. `docker compose -f docker-compose.dev.yml run --rm web uv lock` no produce cambios
   (idempotente).
7. `grep -rn 'requirements' --include='*.md' --include='*.yml' --include='Dockerfile' .`
   sin referencias vivas a `requirements*.txt`.
8. Build de producción + `./deploy.sh` en un entorno de prueba antes del despliegue real.

## Fuera de alcance

- Cambiar de gestor de despliegue (`deploy.sh` y `docker compose` se quedan igual).
- Sustituir `docker-compose.dev.yml`, renombrar stages o tocar `entrypoint.sh`.
- Añadir tests nuevos o reescribir la suite.
- Renovate en lugar de Dependabot.
- Actualizar versiones de dependencias: el primer lock debe reproducir los pines de
  hoy, no mejorarlos.
