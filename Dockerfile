# syntax=docker/dockerfile:1

# --- builder: compila los wheels; el toolchain no llega a la imagen final ---
FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libheif-dev \
    libde265-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -r requirements-dev.txt

# --- runtime: producción, solo requirements.txt desde los wheels ---
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# postgresql-client aporta pg_isready para entrypoint.sh
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN adduser --disabled-password --gecos '' --uid 1000 appuser

COPY requirements.txt ./
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt

# El código pertenece a root: appuser lo lee pero no puede modificarlo.
# Solo media y staticfiles son escribibles.
COPY . .
RUN mkdir -p /app/media /app/staticfiles && \
    chown appuser:appuser /app/media /app/staticfiles

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-"]

# --- dev: último stage para que `build: .` sin target (docker-compose.dev.yml)
# siga teniendo pytest. Producción construye con `target: runtime`.
FROM runtime AS dev

USER root
COPY requirements-dev.txt ./
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r requirements-dev.txt
USER appuser
