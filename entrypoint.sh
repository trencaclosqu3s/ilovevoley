#!/bin/bash
set -e

echo "🚀 Iniciando aplicación..."

# Esperar a que la base de datos esté lista
echo "⏳ Esperando base de datos..."
while ! pg_isready -h db -U ${DB_USER:-volleyuser} > /dev/null 2>&1; do
    sleep 1
done
echo "✅ Base de datos lista"

# Ejecutar el comando que se pase como argumento
exec "$@"
