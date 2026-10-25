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
# ffmpeg extrae fotogramas de Live Photos (ilovevoley.videos.utils).
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    gettext \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos '' --uid 1000 appuser

# El venv lo construye uv en el builder; el runtime no lleva toolchain ni uv.
# Queda como root y de solo lectura para appuser (basta con o+rX).
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
