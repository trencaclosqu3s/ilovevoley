#!/bin/bash
# Script de diagnóstico rápido para producción
# Ejecutar con: bash check_config.sh

echo "=========================================="
echo "  Diagnóstico Rápido - VideosVoley"
echo "=========================================="
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar que estamos en el directorio correcto
if [ ! -f "manage.py" ]; then
    echo -e "${RED}✗ Error: No se encuentra manage.py${NC}"
    echo "  Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi
echo -e "${GREEN}✓ Directorio correcto${NC}"

# 2. Verificar archivo .env
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ Advertencia: No se encuentra archivo .env${NC}"
    echo "  Copia .env.example a .env y configúralo"
else
    echo -e "${GREEN}✓ Archivo .env existe${NC}"
    
    # Verificar variables críticas
    echo ""
    echo "Variables de entorno críticas:"
    echo "-------------------------------"
    
    if grep -q "^DEBUG=False" .env; then
        echo -e "${GREEN}✓ DEBUG=False${NC}"
    else
        echo -e "${YELLOW}⚠ DEBUG no está en False${NC}"
    fi
    
    if grep -q "^ALLOWED_HOSTS=" .env; then
        HOSTS=$(grep "^ALLOWED_HOSTS=" .env | cut -d'=' -f2)
        echo -e "${GREEN}✓ ALLOWED_HOSTS=${HOSTS}${NC}"
    else
        echo -e "${RED}✗ ALLOWED_HOSTS no configurado${NC}"
    fi
    
    if grep -q "^CSRF_TRUSTED_ORIGINS=" .env; then
        ORIGINS=$(grep "^CSRF_TRUSTED_ORIGINS=" .env | cut -d'=' -f2)
        echo -e "${GREEN}✓ CSRF_TRUSTED_ORIGINS=${ORIGINS}${NC}"
    else
        echo -e "${RED}✗ CSRF_TRUSTED_ORIGINS no configurado${NC}"
    fi
    
    if grep -q "^GOOGLE_VISION_ENABLED=True" .env; then
        echo -e "${GREEN}✓ Google Vision habilitado${NC}"
        
        if grep -q "^GOOGLE_APPLICATION_CREDENTIALS=" .env; then
            CREDS=$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" .env | cut -d'=' -f2)
            if [ -f "$CREDS" ]; then
                echo -e "${GREEN}✓ Credenciales existen: ${CREDS}${NC}"
            else
                echo -e "${RED}✗ Archivo de credenciales no existe: ${CREDS}${NC}"
            fi
        else
            echo -e "${RED}✗ GOOGLE_APPLICATION_CREDENTIALS no configurado${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Google Vision deshabilitado${NC}"
    fi
fi

# 3. Verificar directorio media
echo ""
echo "Directorio MEDIA:"
echo "-----------------"
if [ -d "media" ]; then
    echo -e "${GREEN}✓ Directorio media/ existe${NC}"
    
    # Verificar permisos
    if [ -w "media" ]; then
        echo -e "${GREEN}✓ Permisos de escritura: OK${NC}"
    else
        echo -e "${RED}✗ Sin permisos de escritura en media/${NC}"
        echo "  Corregir con: sudo chown -R \$USER:\$USER media/"
    fi
    
    # Verificar subdirectorios
    for dir in images avatars; do
        if [ -d "media/$dir" ]; then
            echo -e "${GREEN}✓ Subdirectorio $dir/ existe${NC}"
        else
            echo -e "${YELLOW}⚠ Subdirectorio $dir/ no existe (se creará automáticamente)${NC}"
        fi
    done
else
    echo -e "${RED}✗ Directorio media/ no existe${NC}"
    echo "  Crear con: mkdir -p media"
fi

# 4. Verificar base de datos
echo ""
echo "Base de Datos:"
echo "--------------"
if python manage.py showmigrations --plan > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Conexión a base de datos: OK${NC}"
    
    # Verificar migraciones pendientes
    PENDING=$(python manage.py showmigrations --plan | grep "\[ \]" | wc -l)
    if [ "$PENDING" -eq 0 ]; then
        echo -e "${GREEN}✓ Todas las migraciones aplicadas${NC}"
    else
        echo -e "${YELLOW}⚠ Hay $PENDING migraciones pendientes${NC}"
        echo "  Aplicar con: python manage.py migrate"
    fi
else
    echo -e "${RED}✗ Error de conexión a base de datos${NC}"
fi

# 5. Ejecutar checks de Django
echo ""
echo "Django System Checks:"
echo "---------------------"
if python manage.py check > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Sin errores en system checks${NC}"
else
    echo -e "${RED}✗ Hay errores en system checks${NC}"
    echo "  Ver detalles con: python manage.py check"
fi

# 6. Comando de diagnóstico personalizado
echo ""
echo "=========================================="
echo "  Ejecutando diagnóstico detallado..."
echo "=========================================="
echo ""

python manage.py check_production_config

echo ""
echo "=========================================="
echo "  Diagnóstico completado"
echo "=========================================="
echo ""
echo "Para más información, consulta:"
echo "  - SOLUCION_RAPIDA.md (pasos inmediatos)"
echo "  - DIAGNOSTICO_ERRORES_PRODUCCION.md (análisis completo)"
echo ""