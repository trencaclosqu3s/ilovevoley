#!/bin/bash
set -e

# Función para verificar si necesitamos ejecutar migraciones y collectstatic
needs_setup() {
    # Debug args
    # echo "DEBUG: args=$@"

    # Si no hay argumentos, es el comando por defecto (server) -> NECESITA SETUP
    if [ $# -eq 0 ]; then
        return 0
    fi

    # Si el comando es explícitamente gunicorn -> NECESITA SETUP
    if [ "$1" = "gunicorn" ]; then
        return 0
    fi

    # Si el comando es python/python3
    if [ "$1" = "python" ] || [ "$1" = "python3" ]; then
        # Caso: python manage.py runserver
        if [ "$2" = "manage.py" ] && [ "$3" = "runserver" ]; then
            return 0
        fi
        # Caso raro: python runserver (si existiera)
        if [ "$2" = "runserver" ]; then
            return 0
        fi
    fi

    # Para todo lo demás (shell, migrate, celery, tests, etc) -> NO NECESITA SETUP
    return 1
}

echo "🚀 Iniciando aplicación..."

# Esperar a que la base de datos esté lista
echo "⏳ Esperando base de datos..."
while ! pg_isready -h db -U ${DB_USER:-volleyuser} > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Base de datos lista"

# Solo ejecutar migraciones y collectstatic si es necesario
if needs_setup "$@"; then
    echo "🔄 Aplicando migraciones..."
    python manage.py migrate --noinput
    
    echo "📁 Recopilando archivos estáticos..."
    python manage.py collectstatic --noinput --clear
    
    echo "✨ ¡Setup completo! Iniciando servidor..."
else
    echo "⚡ Comando directo (saltando setup)..."
fi

# Ejecutar el comando que se pase como argumento
exec "$@"

