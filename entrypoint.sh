#!/bin/bash
set -e

# Función para verificar si necesitamos ejecutar migraciones y collectstatic
needs_setup() {
    # Comandos que NO necesitan setup completo
    local skip_commands=("shell" "shell_plus" "test" "check" "help" "version" "diffsettings" "inspectdb" "dbshell" "showmigrations" "sqlmigrate" "squashmigrations" "makemigrations")
    
    # Si no hay argumentos, asumir que es el servidor web
    if [ $# -eq 0 ]; then
        return 0
    fi
    
    # Verificar si el primer argumento está en la lista de comandos a saltar
    for cmd in "${skip_commands[@]}"; do
        if [ "$1" = "$cmd" ]; then
            return 1
        fi
    done
    
    return 0
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

