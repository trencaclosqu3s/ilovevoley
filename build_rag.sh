#!/bin/bash

# Script de build optimizado para el sistema RAG

echo "🔨 Construyendo contenedores para sistema RAG..."

# Verificar que estamos en el directorio correcto
if [ ! -f "manage.py" ]; then
    echo "❌ Error: Este script debe ejecutarse desde el directorio raíz del proyecto"
    exit 1
fi

# Función para mostrar progreso
show_progress() {
    echo "📋 $1"
}

# Función para mostrar éxito
show_success() {
    echo "✅ $1"
}

# Función para mostrar error
show_error() {
    echo "❌ $1"
}

# 1. Limpiar builds anteriores
show_progress "Limpiando builds anteriores..."
docker-compose -f docker-compose.dev.yml down --volumes --remove-orphans
docker system prune -f
show_success "Limpieza completada"

# 2. Crear directorio para ChromaDB
show_progress "Creando directorio para ChromaDB..."
mkdir -p ./chroma_db
chmod 755 ./chroma_db
show_success "Directorio ChromaDB creado"

# 3. Build paso a paso para mejor debugging
show_progress "Construyendo imagen base..."
docker-compose -f docker-compose.dev.yml build --no-cache db redis
show_success "Servicios base construidos"

show_progress "Construyendo aplicación web..."
docker-compose -f docker-compose.dev.yml build --no-cache web
show_success "Aplicación web construida"

show_progress "Construyendo Celery..."
docker-compose -f docker-compose.dev.yml build --no-cache celery celery-beat
show_success "Celery construido"

# 4. Iniciar servicios
show_progress "Iniciando servicios..."
docker-compose -f docker-compose.dev.yml up -d db redis
show_success "Servicios base iniciados"

# 5. Esperar a que los servicios estén listos
show_progress "Esperando a que los servicios estén listos..."
sleep 15

# 6. Ejecutar migraciones
show_progress "Ejecutando migraciones..."
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate
show_success "Migraciones completadas"

# 7. Crear superusuario si no existe
show_progress "Verificando superusuario..."
if ! docker-compose -f docker-compose.dev.yml exec web python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('Superuser exists:', User.objects.filter(is_superuser=True).exists())" | grep -q "True"; then
    echo "👤 Creando superusuario..."
    docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser --noinput --username admin --email admin@example.com
    docker-compose -f docker-compose.dev.yml exec web python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); u = User.objects.get(username='admin'); u.set_password('admin123'); u.save()"
    show_success "Superusuario creado (admin/admin123)"
else
    show_success "Superusuario ya existe"
fi

# 8. Iniciar todos los servicios
show_progress "Iniciando todos los servicios..."
docker-compose -f docker-compose.dev.yml up -d
show_success "Todos los servicios iniciados"

# 9. Mostrar información final
echo ""
echo "🎉 ¡Build completado exitosamente!"
echo ""
echo "📋 Información del sistema:"
echo "   • Aplicación web: http://localhost:8000"
echo "   • Admin: http://localhost:8000/admin (admin/admin123)"
echo "   • Chat RAG: http://localhost:8000/rag/"
echo ""
echo "🔧 Comandos útiles:"
echo "   • Ver logs: docker-compose -f docker-compose.dev.yml logs -f"
echo "   • Parar servicios: docker-compose -f docker-compose.dev.yml down"
echo "   • Rebuild: ./build_rag.sh"
echo ""
echo "¡Sistema RAG listo para usar! 🤖"