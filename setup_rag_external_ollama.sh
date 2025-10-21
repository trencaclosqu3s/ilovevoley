#!/bin/bash

# Script de configuración para sistema RAG con Ollama externo

echo "🚀 Configurando sistema RAG con Ollama externo..."

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

# 2. Solicitar IP del servidor Ollama
echo ""
echo "🔧 Configuración de Ollama externo:"
read -p "¿Cuál es la IP de tu servidor Ollama? (ej: 192.168.1.100): " OLLAMA_IP

if [ -z "$OLLAMA_IP" ]; then
    show_error "Debes proporcionar la IP del servidor Ollama"
    exit 1
fi

# 3. Verificar conectividad con Ollama
show_progress "Verificando conexión con Ollama en $OLLAMA_IP:11434..."
if curl -s --connect-timeout 5 "http://$OLLAMA_IP:11434/api/tags" > /dev/null; then
    show_success "Conexión con Ollama exitosa"
else
    show_error "No se puede conectar con Ollama en $OLLAMA_IP:11434"
    echo "Verifica que:"
    echo "  - Ollama esté ejecutándose en el servidor"
    echo "  - El puerto 11434 esté abierto"
    echo "  - La IP sea correcta"
    exit 1
fi

# 4. Verificar que phi3:mini esté disponible
show_progress "Verificando modelo phi3:mini..."
if curl -s "http://$OLLAMA_IP:11434/api/tags" | grep -q "phi3:mini"; then
    show_success "Modelo phi3:mini encontrado"
else
    echo "⚠️  Modelo phi3:mini no encontrado. Modelos disponibles:"
    curl -s "http://$OLLAMA_IP:11434/api/tags" | grep -o '"name":"[^"]*"' | sed 's/"name":"//g' | sed 's/"//g'
    echo ""
    read -p "¿Continuar de todos modos? (y/N): " CONTINUE
    if [[ ! $CONTINUE =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 5. Crear archivo .env con la configuración
show_progress "Creando archivo de configuración..."
cat > .env << EOF
# Configuración para sistema RAG con Ollama externo
OLLAMA_HOST=http://$OLLAMA_IP:11434
CHROMA_COLLECTION_NAME=videosvoley_docs
CHROMA_PERSIST_DIR=./chroma_db
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
DEFAULT_OLLAMA_MODEL=phi3:mini
EOF
show_success "Archivo .env creado"

# 6. Crear directorio para ChromaDB
show_progress "Creando directorio para ChromaDB..."
mkdir -p ./chroma_db
chmod 755 ./chroma_db
show_success "Directorio ChromaDB creado"

# 7. Construir e iniciar servicios
show_progress "Construyendo e iniciando servicios Docker..."
docker-compose -f docker-compose.dev.yml up -d --build
show_success "Servicios construidos e iniciados"

# 8. Esperar a que los servicios estén listos
show_progress "Esperando a que los servicios estén listos..."
sleep 15

# 10. Ejecutar migraciones
show_progress "Ejecutando migraciones de base de datos..."
docker-compose -f docker-compose.dev.yml exec web python manage.py makemigrations
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate
show_success "Migraciones completadas"

# 10.5. Inicializar sistema RAG
show_progress "Inicializando sistema RAG..."
docker-compose -f docker-compose.dev.yml exec web python manage.py init_rag
show_success "Sistema RAG inicializado"

# 11. Crear superusuario si no existe
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

# 12. Probar conexión con Ollama desde el contenedor
show_progress "Probando conexión con Ollama desde el contenedor..."
if docker-compose -f docker-compose.dev.yml exec web python -c "
import requests
import os
ollama_host = os.getenv('OLLAMA_HOST', 'http://$OLLAMA_IP:11434')
try:
    response = requests.get(f'{ollama_host}/api/tags', timeout=5)
    if response.status_code == 200:
        print('Conexión exitosa')
    else:
        print('Error de conexión')
except Exception as e:
    print(f'Error: {e}')
"; then
    show_success "Conexión con Ollama verificada desde el contenedor"
else
    show_error "Error conectando con Ollama desde el contenedor"
    echo "Verifica la configuración de red entre contenedores y servidor"
fi

# 13. Indexar documentos iniciales
show_progress "Indexando documentos iniciales..."
docker-compose -f docker-compose.dev.yml exec web python manage.py index_documents --limit 50
show_success "Documentos indexados"

# 14. Iniciar todos los servicios
show_progress "Iniciando todos los servicios..."
docker-compose -f docker-compose.dev.yml up -d
show_success "Todos los servicios iniciados"

# 15. Mostrar información final
echo ""
echo "🎉 ¡Sistema RAG configurado exitosamente con Ollama externo!"
echo ""
echo "📋 Información del sistema:"
echo "   • Aplicación web: http://localhost:8000"
echo "   • Admin: http://localhost:8000/admin (admin/admin123)"
echo "   • Chat RAG: http://localhost:8000/rag/"
echo "   • Ollama externo: http://$OLLAMA_IP:11434"
echo "   • Modelo por defecto: phi3:mini"
echo ""
echo "🔧 Comandos útiles:"
echo "   • Ver logs: docker-compose -f docker-compose.dev.yml logs -f"
echo "   • Parar servicios: docker-compose -f docker-compose.dev.yml down"
echo "   • Reindexar: docker-compose -f docker-compose.dev.yml exec web python manage.py index_documents"
echo "   • Limpiar RAG: docker-compose -f docker-compose.dev.yml exec web python manage.py clear_rag_data --confirm"
echo ""
echo "📚 Documentación: Ver rag/README.md para más detalles"
echo ""
echo "¡Disfruta usando el sistema RAG con tu Ollama externo! 🤖"