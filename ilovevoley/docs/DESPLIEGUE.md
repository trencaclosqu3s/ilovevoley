# 🚀 Guía Rápida de Despliegue

## Para desplegar en producción

```bash
./deploy.sh
```

**¡Eso es todo!** 🎉

## ¿Qué hace automáticamente?

El sistema ahora ejecuta automáticamente:

✅ **Migraciones de base de datos** - `python manage.py migrate`  
✅ **Recopilación de archivos estáticos** - `python manage.py collectstatic`  
✅ **Espera a que la base de datos esté lista**  
✅ **Inicia el servidor web**

Todo esto se ejecuta gracias al script `entrypoint.sh` que se ejecuta cada vez que inicia el contenedor.

## Comandos útiles

### Ver logs en tiempo real
```bash
docker compose logs -f web
```

### Reiniciar solo el servidor web
```bash
docker compose restart web
```

### Reconstruir todo desde cero
```bash
docker compose down
docker compose build
docker compose up -d
```

### Limpiar archivos estáticos (si hay problemas)
```bash
sudo rm -rf /opt/videosvoley/static/*
./deploy.sh
```

## Estructura de archivos estáticos

- `ilovevoley/static/` - **Código fuente** (se sube a git)
- `/opt/videosvoley/static/` - **Archivos recopilados** en producción (volumen Docker)
- `staticfiles/` - Archivos recopilados locales (ignorado por git)

## Flujo de trabajo

1. Haces cambios en tu código (incluyendo archivos en `ilovevoley/static/`)
2. Haces commit y push a git
3. En el servidor ejecutas `./deploy.sh`
4. El sistema automáticamente:
   - Descarga los cambios
   - Reconstruye las imágenes
   - Ejecuta migraciones
   - Recopila archivos estáticos
   - Reinicia los servicios

## Notas importantes

- **No ejecutes `collectstatic` manualmente** - Se hace automáticamente
- **No ejecutes `migrate` manualmente** - Se hace automáticamente
- **Los archivos en `ilovevoley/static/` SÍ se suben a git** - Son código fuente
- **Los archivos en `/staticfiles/` NO se suben a git** - Son generados

Para más detalles, consulta `SOLUCION_STATIC.md`.

