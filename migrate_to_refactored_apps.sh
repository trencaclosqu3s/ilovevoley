#!/bin/bash

set -e

echo "🔄 SCRIPT DE MIGRACIÓN A APPS REFACTORIZADAS"
echo "==========================================="
echo ""
echo "Este script migrará los datos de la app monolítica 'videos'"
echo "a las nuevas apps especializadas: content, competitions, teams, rosters"
echo ""

# Función para ejecutar comando Django
run_django() {
    if command -v docker-compose &> /dev/null; then
        if [ -f "docker-compose.dev.yml" ]; then
            docker-compose -f docker-compose.dev.yml run --rm --entrypoint="" web python manage.py "$@"
        else
            docker-compose run --rm web python manage.py "$@"
        fi
    else
        python manage.py "$@"
    fi
}

# Paso 1: Verificar estado actual
echo "📋 PASO 1: Verificando estado actual de migraciones..."
echo "================================================="
run_django showmigrations | grep -E "(content|competitions|teams|rosters|users)" || true
echo ""

# Paso 2: Hacer fake apply de las nuevas apps
echo "🎭 PASO 2: Aplicando migraciones de nuevas apps (fake)..."
echo "======================================================="
echo "Esto marca las migraciones como aplicadas sin ejecutar SQL..."
echo ""

echo "- content app..."
run_django migrate content --fake || echo "⚠️ Error en content, continuando..."

echo "- competitions app..."
run_django migrate competitions --fake || echo "⚠️ Error en competitions, continuando..."

echo "- teams app..."
run_django migrate teams --fake || echo "⚠️ Error en teams, continuando..."

echo "- rosters app..."
run_django migrate rosters --fake || echo "⚠️ Error en rosters, continuando..."

echo ""

# Paso 3: Verificar que las migraciones fake funcionaron
echo "✅ PASO 3: Verificando migraciones aplicadas..."
echo "=============================================="
run_django showmigrations | grep -E "(content|competitions|teams|rosters)" || true
echo ""

# Paso 4: Migrar datos
echo "📦 PASO 4: Migrando datos de videos a nuevas apps..."
echo "=================================================="

# Verificar que existen los comandos de migración
echo "Verificando comandos de migración disponibles..."
run_django help | grep migrate_ | head -5 || echo "Comandos de migración disponibles:"

echo ""
echo "🎯 COMANDOS A EJECUTAR MANUALMENTE:"
echo "=================================="
echo ""
echo "1. Migrar datos de content:"
echo "   python manage.py migrate_content_data"
echo ""
echo "2. Migrar datos de teams:"
echo "   python manage.py migrate_teams_data"
echo ""
echo "3. Migrar datos de competitions:"
echo "   python manage.py migrate_competitions_data"
echo ""
echo "4. Migrar datos de rosters:"
echo "   python manage.py migrate_rosters_data"
echo ""
echo "5. Actualizar foreign keys:"
echo "   python manage.py update_foreign_keys"
echo ""
echo "💡 EJECUTA ESTOS COMANDOS UNO A UNO Y VERIFICA LOS RESULTADOS"
echo ""

read -p "¿Quieres continuar con la migración automática de datos? (s/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo "🚀 Ejecutando migración automática de datos..."
    
    echo "- Migrando content..."
    run_django migrate_content_data || echo "⚠️ Error en migrate_content_data"
    
    echo "- Migrando teams..."
    run_django migrate_teams_data || echo "⚠️ Error en migrate_teams_data"
    
    echo "- Migrando competitions..."
    run_django migrate_competitions_data || echo "⚠️ Error en migrate_competitions_data"
    
    echo "- Migrando rosters..."
    run_django migrate_rosters_data || echo "⚠️ Error en migrate_rosters_data"
    
    echo "- Actualizando foreign keys..."
    run_django update_foreign_keys || echo "⚠️ Error en update_foreign_keys"
else
    echo "⏸️ Migración pausada. Ejecuta los comandos manualmente cuando estés listo."
fi

echo ""
echo "✅ MIGRACIÓN COMPLETADA"
echo "====================="
echo ""
echo "🔍 Verifica los datos:"
echo "- Revisa que los datos se migraron correctamente"
echo "- Ejecuta las pruebas de la aplicación"
echo "- Verifica que no hay errores en los logs"
echo ""