# Sistema de Despliegue y Estáticos

## Problema Original Resuelto ✅
- El archivo `auto_filters.js` no se estaba subiendo a git por la configuración del `.gitignore`
- Al hacer `collectstatic` manualmente daba error de permisos: `PermissionError: [Errno 13] Permission denied`

## Causas Identificadas
1. **`.gitignore` demasiado amplio**: Tenía `static/` que ignoraba TODOS los directorios static, incluyendo el código fuente en `ilovevoley/static/`
2. **Permisos incorrectos en Docker**: El Dockerfile creaba directorios como `root` y luego cambiaba a `appuser`, causando conflictos de permisos
3. **Proceso manual propenso a errores**: Había que recordar ejecutar `collectstatic` en cada despliegue

## Soluciones Aplicadas ✨

### 1. `.gitignore` Corregido
**Antes:**
```gitignore
static/
```

**Ahora:**
```gitignore
# Ignorar staticfiles recopilados, pero NO el directorio source static
/staticfiles/
```

✅ Ahora `ilovevoley/static/` se sube a git, pero `/staticfiles/` (archivos recopilados) se ignora.

### 2. `Dockerfile` Mejorado
Cambios principales:
- ✅ Usuario `appuser` con UID 1000 se crea ANTES de copiar archivos
- ✅ Uso de `COPY --chown=appuser:appuser` para permisos correctos
- ✅ Directorios creados con permisos correctos desde el inicio
- ✅ **Script `entrypoint.sh` configurado** para automatización

### 3. `entrypoint.sh` mínimo
Desde #118 el entrypoint solo espera a la base de datos y ejecuta el comando. **Ya no
ejecuta migraciones ni `collectstatic`**: se hacen una sola vez en `deploy.sh`, antes del
`up`, y si fallan hay rollback sin tocar los contenedores en marcha.

### 4. Script de Despliegue General `deploy.sh`

Para desplegar en producción, simplemente ejecuta:

```bash
./deploy.sh
```

Este script:
1. Descarga los últimos cambios de git
2. Reconstruye las imágenes Docker
3. Aplica migraciones (`run --rm web ... migrate`)
4. Recopila estáticos (`run --rm web ... collectstatic --noinput`, sin `--clear`)
5. Levanta los servicios, recarga nginx y comprueba `/healthz` (con rollback si falla)

## Verificación

Después de ejecutar los comandos, verifica que:

1. **El archivo existe en el servidor:**
   ```bash
   ls -la /opt/videosvoley/static/js/auto_filters.js
   ```
   Debería mostrar permisos `-rw-r--r--` y propietario `1000:1000`

2. **El archivo es accesible vía web:**
   Abre en tu navegador: `https://tu-dominio.com/static/js/auto_filters.js`

3. **No hay errores 404 en la consola del navegador**

## 🚀 Cómo Desplegar de Ahora en Adelante

### En desarrollo local:
Los archivos estáticos se sirven automáticamente por Django. No necesitas hacer nada especial.

### En producción:

```bash
./deploy.sh
```

### Si haces el despliegue a mano (p. ej. al cambiar claves en los `.env`):

```bash
git pull
docker compose build
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py collectstatic --noinput
docker compose up -d --remove-orphans
```

**Importante:** `collectstatic` NO es automático. Si se omite, los estáticos nuevos dan 404
(`ForgivingManifestStaticFilesStorage` sirve la URL sin hash cuando el fichero no está en el
manifest, y nginx no encuentra ese fichero). Si el proceso `web` conserva el manifest viejo,
`docker compose restart web`.

### Al agregar nuevos archivos estáticos:

1. Colócalos en `ilovevoley/static/`
2. Haz commit y push a git
3. En producción ejecuta `./deploy.sh`

## 📁 Archivos Creados/Modificados

- ✅ `.gitignore` - Ahora solo ignora `/staticfiles/` en la raíz
- ✅ `Dockerfile` - Permisos correctos + entrypoint configurado
- ✅ `entrypoint.sh` - Espera a la base de datos (sin migraciones ni collectstatic desde #118)
- ✅ `deploy.sh` - **Script de despliegue para producción** (úsalo siempre)
- ✅ `docker-compose.yml` - Celery espera a web para evitar problemas
- ✅ `SOLUCION_STATIC.md` - Esta documentación

## 🔧 Troubleshooting

### Un estático nuevo da 404 en producción
Falta `collectstatic`. Comprueba:

```bash
grep -o '"js/<fichero>[^,]*' /opt/videosvoley/static/staticfiles.json
docker compose run --rm web python manage.py collectstatic --noinput
```

### Si necesitas limpiar completamente los archivos estáticos:

```bash
sudo rm -rf /opt/videosvoley/static/*
./deploy.sh
```

`deploy.sh` volverá a recopilar todo.
