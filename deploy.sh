#!/bin/bash
# Script de despliegue general para producción con validación de salud y rollback

set -e  # Salir si hay algún error inesperado inicial

echo "🚀 Iniciando despliegue..."

# Guardar commit previo para rollback en caso de fallo
PREV_COMMIT=$(git rev-parse HEAD)
MIGRATIONS_APPLIED=false

# Actualizar código desde git
echo "📥 Descargando últimos cambios..."
git pull

# SHA del commit desplegado, usado por Sentry para el release tracking
export GIT_SHA=$(git rev-parse --short HEAD)

# El bind-mount de nginx.conf no recarga el proceso: hay que reload/recreate.
reload_nginx() {
    echo "🔄 Aplicando nginx.conf al proceso nginx..."
    if ! docker compose exec -T nginx nginx -t; then
        echo "❌ nginx -t falló; la configuración no es válida."
        return 1
    fi
    # nginx -s reload puede colgarse; timeout corto y fallback a recreate.
    if timeout 15 docker compose exec -T nginx nginx -s reload; then
        echo "✅ nginx recargado."
        return 0
    fi
    echo "⚠️ reload no respondió a tiempo; recreando contenedor nginx..."
    if ! docker compose up -d --force-recreate --no-deps nginx; then
        echo "❌ No se pudo recrear nginx."
        return 1
    fi
    echo "✅ nginx recreado."
}

# Función de rollback
rollback() {
    echo ""
    echo "⚠️ Falló la validación del despliegue. Iniciando rollback a $PREV_COMMIT..."
    if [ "$MIGRATIONS_APPLIED" = "true" ]; then
        echo "⚠️ ATENCIÓN: Las migraciones de base de datos ya se habían aplicado."
        echo "   Si el nuevo esquema no es compatible hacia atrás con $PREV_COMMIT,"
        echo "   podría ser necesaria una intervención manual de migración reversa."
    fi
    git reset --hard "$PREV_COMMIT"
    export GIT_SHA=$(git rev-parse --short HEAD)
    docker compose build
    docker compose up -d --remove-orphans
    reload_nginx || true
    echo "🔄 Rollback completado a la versión $PREV_COMMIT."
    exit 1
}

# Reconstruir imágenes si hay cambios en Dockerfile o requirements
echo "🏗️  Reconstruyendo imágenes..."
docker compose build

# Ejecutar migraciones como paso único previo
echo "🔄 Aplicando migraciones de base de datos..."
if ! docker compose run --rm web python manage.py migrate; then
    echo "❌ Error al aplicar migraciones."
    rollback
fi
MIGRATIONS_APPLIED=true

# Recopilar archivos estáticos sin --clear para evitar ventanas temporales sin estáticos
echo "📁 Recopilando archivos estáticos..."
if ! docker compose run --rm web python manage.py collectstatic --noinput; then
    echo "❌ Error al recopilar archivos estáticos."
    rollback
fi

# Compilar catálogos de traducción (.po -> .mo)
echo "🌍 Compilando mensajes de traducción..."
if ! docker compose run --rm web python manage.py compilemessages; then
    echo "❌ Error al compilar los mensajes de traducción."
    rollback
fi

# Actualizar y reiniciar contenedores
echo "♻️  Actualizando servicios (mínimo downtime)..."
if ! docker compose up -d --remove-orphans; then
    echo "❌ Error al levantar los contenedores."
    rollback
fi

# nginx.conf va por bind-mount: up -d no aplica cambios de conf en memoria.
if ! reload_nginx; then
    echo "❌ Error aplicando la configuración de nginx."
    rollback
fi

# Comprobar salud del servicio (/healthz)
echo "🩺 Verificando salud del servicio (/healthz)..."
HEALTH_OK=false
MAX_RETRIES=10
RETRY_INTERVAL=3

for i in $(seq 1 $MAX_RETRIES); do
    echo "⏳ Comprobando healthcheck (intento $i/$MAX_RETRIES)..."
    if docker compose exec -T web curl --fail -s http://localhost:8000/healthz > /dev/null 2>&1; then
        HEALTH_OK=true
        break
    fi
    sleep $RETRY_INTERVAL
done

if [ "$HEALTH_OK" != "true" ]; then
    echo "❌ El contenedor web no responde saludablemente en /healthz tras $MAX_RETRIES intentos."
    rollback
fi

# Verificar estado
echo ""
echo "📊 Estado de los servicios:"
docker compose ps

echo ""
echo "✅ ¡Despliegue completado con éxito!"
echo ""
echo "📝 Para ver los logs:"
echo "    docker compose logs -f web"
