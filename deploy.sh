#!/bin/bash
# Script de despliegue general para producción
# Se ejecuta automáticamente collectstatic y migraciones gracias al entrypoint.sh

set -e  # Salir si hay algún error

echo "🚀 Iniciando despliegue..."

# Actualizar código desde git
echo "📥 Descargando últimos cambios..."
git pull

# Reconstruir imágenes si hay cambios en Dockerfile o requirements
echo "🏗️  Reconstruyendo imágenes..."
docker compose build

# Reiniciar servicios
echo "♻️  Reiniciando servicios..."
docker compose down
docker compose up -d

# Esperar a que los servicios inicien
echo "⏳ Esperando a que los servicios inicien..."
sleep 5

# Verificar estado
echo ""
echo "📊 Estado de los servicios:"
docker compose ps

echo ""
echo "✅ ¡Despliegue completado!"
echo ""
echo "💡 Nota: Las migraciones y collectstatic se ejecutan automáticamente"
echo "    gracias al script entrypoint.sh"
echo ""
echo "📝 Para ver los logs:"
echo "    docker compose logs -f web"

