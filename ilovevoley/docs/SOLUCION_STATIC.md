# Sistema de Despliegue Automático

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

### 3. Nuevo `entrypoint.sh` (⭐ Automatización)
Este script se ejecuta **automáticamente** cada vez que inicia un contenedor:
- ✅ Espera a que la base de datos esté lista
- ✅ Ejecuta migraciones automáticamente
- ✅ **Ejecuta `collectstatic` automáticamente**
- ✅ Inicia el servidor

**¡Ya no necesitas ejecutar `collectstatic` manualmente!**

### 4. Script de Despliegue General `deploy.sh`

Para desplegar en producción, simplemente ejecuta:

```bash
./deploy.sh
```

Este script:
1. Descarga los últimos cambios de git
2. Reconstruye las imágenes Docker
3. Reinicia los servicios
4. **Collectstatic y migraciones se ejecutan automáticamente** gracias al entrypoint

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

**¡Es súper simple ahora!**

```bash
./deploy.sh
```

Eso es todo. El script se encarga de:
- ✅ Descargar cambios de git
- ✅ Reconstruir imágenes
- ✅ Reiniciar servicios
- ✅ Collectstatic automático (vía entrypoint)
- ✅ Migraciones automáticas (vía entrypoint)

### Si prefieres hacerlo manualmente:

```bash
git pull
docker compose build
docker compose down
docker compose up -d
```

**Nota:** Ya NO necesitas ejecutar `collectstatic` manualmente. Se ejecuta automáticamente cuando inicia el contenedor `web`.

### Al agregar nuevos archivos estáticos:

1. Colócalos en `ilovevoley/static/`
2. Haz commit y push a git
3. En producción ejecuta `./deploy.sh`
4. ¡Listo! El `collectstatic` se ejecuta automáticamente

## 📁 Archivos Creados/Modificados

- ✅ `.gitignore` - Ahora solo ignora `/staticfiles/` en la raíz
- ✅ `Dockerfile` - Permisos correctos + entrypoint configurado
- ✅ `entrypoint.sh` - **Script de automatización** (migraciones + collectstatic)
- ✅ `deploy.sh` - **Script de despliegue para producción** (úsalo siempre)
- ✅ `docker-compose.yml` - Celery espera a web para evitar problemas
- ✅ `SOLUCION_STATIC.md` - Esta documentación

## 🎯 Beneficios del Nuevo Sistema

1. **Menos errores**: No olvidas ejecutar `collectstatic`
2. **Más rápido**: Un solo comando para desplegar
3. **Más seguro**: Permisos correctos desde el inicio
4. **Más limpio**: No hay que recordar comandos manuales
5. **Migraciones automáticas**: También se aplican automáticamente

## 🔧 Troubleshooting

### Si alguna vez necesitas limpiar completamente los archivos estáticos:

```bash
sudo rm -rf /opt/videosvoley/static/*
./deploy.sh
```

El `entrypoint.sh` volverá a recopilar todo automáticamente.

### Para ver qué está haciendo el entrypoint:

```bash
docker compose logs web
```

Verás mensajes como:
```
🚀 Iniciando aplicación...
⏳ Esperando base de datos...
✅ Base de datos lista
🔄 Aplicando migraciones...
📁 Recopilando archivos estáticos...
✨ ¡Listo! Iniciando servidor...
```

