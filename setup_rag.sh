#!/bin/bash

# Script de configuración inicial para el sistema RAG de VideosVoley

echo "🚀 Configurando sistema RAG para VideosVoley..."

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

# 1. Verificar Docker
show_progress "Verificando Docker..."
if ! command -v docker &> /dev/null; then
    show_error "Docker no está instalado. Por favor instala Docker primero."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    show_error "Docker Compose no está instalado. Por favor instala Docker Compose primero."
    exit 1
fi
show_success "Docker y Docker Compose están disponibles"

# 2. Crear directorio para ChromaDB
show_progress "Creando directorio para ChromaDB..."
mkdir -p ./chroma_db
chmod 755 ./chroma_db
show_success "Directorio ChromaDB creado"

# 3. Iniciar servicios
show_progress "Iniciando servicios Docker..."
docker-compose -f docker-compose.dev.yml up -d db redis ollama
show_success "Servicios base iniciados"

# 4. Esperar a que los servicios estén listos
show_progress "Esperando a que los servicios estén listos..."
sleep 10

# 5. Instalar dependencias Python
show_progress "Instalando dependencias Python..."
docker-compose -f docker-compose.dev.yml exec web pip install -r requirements.txt
show_success "Dependencias instaladas"

# 6. Ejecutar migraciones
show_progress "Ejecutando migraciones de base de datos..."
docker-compose -f docker-compose.dev.yml exec web python manage.py makemigrations
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate
show_success "Migraciones completadas"

# 7. Instalar modelos de Ollama
show_progress "Instalando modelos de Ollama..."
echo "📥 Descargando llama3.2 (esto puede tomar varios minutos)..."
docker-compose -f docker-compose.dev.yml exec ollama ollama pull llama3.2

echo "📥 Descargando llama3.1..."
docker-compose -f docker-compose.dev.yml exec ollama ollama pull llama3.1

echo "📥 Descargando mistral..."
docker-compose -f docker-compose.dev.yml exec ollama ollama pull mistral

echo "📥 Descargando codellama..."
docker-compose -f docker-compose.dev.yml exec ollama ollama pull codellama

show_success "Modelos de Ollama instalados"

# 8. Verificar que Ollama funciona
show_progress "Verificando conexión con Ollama..."
if docker-compose -f docker-compose.dev.yml exec ollama ollama list | grep -q "llama3.2"; then
    show_success "Ollama está funcionando correctamente"
else
    show_error "Error verificando Ollama. Revisa los logs: docker-compose logs ollama"
fi

# 9. Crear superusuario si no existe
show_progress "Verificando superusuario..."
if ! docker-compose -f docker-compose.dev.yml exec web python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('Superuser exists:', User.objects.filter(is_superuser=True).exists())" | grep -q "True"; then
    echo "👤 Creando superusuario..."
    docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser --noinput --username admin --email admin@example.com
    echo "🔑 Contraseña temporal: admin123 (cámbiala después)"
    docker-compose -f docker-compose.dev.yml exec web python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); u = User.objects.get(username='admin'); u.set_password('admin123'); u.save()"
    show_success "Superusuario creado (admin/admin123)"
else
    show_success "Superusuario ya existe"
fi

# 10. Indexar documentos iniciales
show_progress "Indexando documentos iniciales..."
docker-compose -f docker-compose.dev.yml exec web python manage.py index_documents --limit 50
show_success "Documentos indexados"

# 11. Iniciar todos los servicios
show_progress "Iniciando todos los servicios..."
docker-compose -f docker-compose.dev.yml up -d
show_success "Todos los servicios iniciados"

# 12. Mostrar información final
echo ""
echo "🎉 ¡Sistema RAG configurado exitosamente!"
echo ""
echo "📋 Información del sistema:"
echo "   • Aplicación web: http://localhost:8000"
echo "   • Admin: http://localhost:8000/admin (admin/admin123)"
echo "   • Chat RAG: http://localhost:8000/rag/"
echo "   • Ollama: http://localhost:11434"
echo ""
echo "🔧 Comandos útiles:"
echo "   • Ver logs: docker-compose -f docker-compose.dev.yml logs -f"
echo "   • Parar servicios: docker-compose -f docker-compose.dev.yml down"
echo "   • Reindexar: docker-compose -f docker-compose.dev.yml exec web python manage.py index_documents"
echo "   • Limpiar RAG: docker-compose -f docker-compose.dev.yml exec web python manage.py clear_rag_data --confirm"
echo ""
echo "📚 Documentación: Ver rag/README.md para más detalles"
echo ""
echo "¡Disfruta usando el sistema RAG! 🤖"