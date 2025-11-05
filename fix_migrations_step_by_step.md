# Guía Paso a Paso: Migración a Apps Refactorizadas

## Problema Actual
- La BBDD tiene datos de producción frescos
- Las migraciones de `users` dependen de apps nuevas que no están aplicadas
- Necesitamos hacer "fake apply" de las nuevas apps sin perder datos

## Pasos para Producción

### 1. Verificar Estado Inicial
```bash
python manage.py showmigrations | grep -E "(content|competitions|teams|rosters|users)"
```

### 2. Aplicar Migraciones de Nuevas Apps (FAKE)
Estas migraciones no ejecutan SQL, solo marcan como aplicadas:

```bash
# Content app
python manage.py migrate content --fake

# Teams app  
python manage.py migrate teams --fake

# Competitions app
python manage.py migrate competitions --fake

# Rosters app
python manage.py migrate rosters --fake
```

### 3. Verificar que las Fake Applications Funcionaron
```bash
python manage.py showmigrations | grep -E "(content|competitions|teams|rosters)"
```
Deberían mostrar todas con `[X]`.

### 4. Aplicar Migraciones Pendientes (si las hay)
```bash
python manage.py migrate --plan
python manage.py migrate
```

### 5. Migrar Datos de videos a Nuevas Apps
```bash
# Migrar categorías, videos, imágenes, comentarios
python manage.py migrate_content_data

# Migrar clubs y teams  
python manage.py migrate_teams_data

# Migrar ligas, partidos, clasificaciones
python manage.py migrate_competitions_data

# Migrar personas y roles
python manage.py migrate_rosters_data
```

### 6. Actualizar Foreign Keys
```bash
python manage.py update_foreign_keys
```

### 7. Verificar Integridad
```bash
python manage.py verify_migration_integrity
```

## Comandos Docker
Si usas Docker, reemplaza `python manage.py` con:
```bash
docker-compose exec web python manage.py
# o
docker-compose -f docker-compose.dev.yml run --rm --entrypoint="" web python manage.py
```

## Rollback si Algo Sale Mal
1. Restaurar backup de BBDD
2. Revisar migraciones problemáticas
3. Ajustar dependencias y repetir

## Verificación Final
- Comprobar que la app funciona correctamente
- Verificar que no hay errores en admin
- Probar creación/edición de contenido
- Verificar que las relaciones funcionan