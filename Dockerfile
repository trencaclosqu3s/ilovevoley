# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libheif-dev \
    libde265-dev \
    build-essential \
    gcc \
    pkg-config \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario antes de instalar dependencias
RUN adduser --disabled-password --gecos '' --uid 1000 appuser

# Instalar dependencias Python
COPY requirements.txt requirements-dev.txt ./

# Actualizar pip y herramientas de compilación
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip setuptools wheel

# requirements-dev.txt arranca con `-r requirements.txt`, así que esta única
# instalación cubre producción y desarrollo. El sobrecoste en la imagen de
# producción son dos paquetes de test.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-dev.txt

# Copiar código
COPY --chown=appuser:appuser . .

# Crear directorios necesarios con el usuario correcto
RUN mkdir -p /app/media /app/staticfiles && \
    chown -R appuser:appuser /app/media /app/staticfiles

# Copiar y dar permisos al script de entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Cambiar al usuario no privilegiado
USER appuser

# Configurar entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Comando por defecto (será sobrescrito por docker-compose)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
