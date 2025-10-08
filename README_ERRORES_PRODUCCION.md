# 🚨 Guía de Solución - Errores 500 en Producción

> **TL;DR**: Ejecuta `bash check_config.sh` en tu servidor de producción y sigue las instrucciones.

---

## 📋 Índice

1. [Inicio Rápido](#-inicio-rápido)
2. [Archivos de Ayuda](#-archivos-de-ayuda)
3. [Problemas Comunes](#-problemas-comunes)
4. [Comandos Útiles](#-comandos-útiles)

---

## 🚀 Inicio Rápido

### Paso 1: Diagnóstico (2 minutos)

```bash
# Conectarse al servidor de producción
ssh usuario@tu-servidor

# Ir al directorio del proyecto
cd /ruta/a/videosvoley

# Ejecutar diagnóstico
bash check_config.sh
```

### Paso 2: Solucionar (5 minutos)

El script te dirá exactamente qué está mal. Los problemas más comunes:

#### ❌ Error en Login con Google

**Síntoma**: Error 500 al hacer clic en "Iniciar sesión con Google"

**Solución**:
```bash
python manage.py shell
```
```python
from django.contrib.sites.models import Site
site = Site.objects.get(id=1)
site.domain = 'tu-dominio-produccion.com'  # Cambiar por tu dominio real
site.save()
exit()
```

Luego ir a `/admin/socialaccount/socialapp/` y verificar que el Site está asociado.

#### ❌ Error en Subida de Imágenes

**Síntoma**: Error 500 al intentar subir una foto

**Solución rápida** (deshabilitar Vision API):
```bash
# Editar .env
nano .env

# Cambiar estas líneas:
GOOGLE_VISION_ENABLED=False
AUTO_MODERATION_ENABLED=False

# Guardar y reiniciar
sudo systemctl restart tu-servicio
# O: docker-compose restart web
```

**Solución permanente** (configurar Vision API):
Ver [SOLUCION_RAPIDA.md](SOLUCION_RAPIDA.md#para-google-vision-api)

### Paso 3: Verificar (1 minuto)

```bash
# Probar login con Google
# → Abrir navegador en modo incógnito
# → Ir a tu sitio
# → Clic en "Iniciar sesión con Google"
# → Debe funcionar ✅

# Probar subida de imágenes
# → Iniciar sesión
# → Subir una imagen de prueba
# → Debe funcionar ✅
```

---

## 📚 Archivos de Ayuda

### Para Usuarios Rápidos

| Archivo | Descripción | Tiempo |
|---------|-------------|--------|
| **[SOLUCION_RAPIDA.md](SOLUCION_RAPIDA.md)** | Pasos específicos para solucionar | 5-10 min |
| **check_config.sh** | Script de diagnóstico automático | 2 min |

### Para Análisis Profundo

| Archivo | Descripción |
|---------|-------------|
| **[DIAGNOSTICO_ERRORES_PRODUCCION.md](DIAGNOSTICO_ERRORES_PRODUCCION.md)** | Análisis técnico completo |
| **[RESUMEN_MEJORAS.md](RESUMEN_MEJORAS.md)** | Mejoras implementadas en el código |

---

## 🔍 Problemas Comunes

### 1. Login con Google → Error 500

**Causa**: Site.domain incorrecto

**Verificar**:
```bash
python manage.py shell -c "from django.contrib.sites.models import Site; print(Site.objects.get(id=1).domain)"
```

**Debe mostrar**: `tu-dominio-produccion.com`

**Si muestra**: `example.com` o `localhost` → **CORREGIR**

---

### 2. Subida de Imágenes → Error 500

**Causa**: Credenciales de Google Vision API no configuradas

**Verificar**:
```bash
grep GOOGLE_VISION_ENABLED .env
grep GOOGLE_APPLICATION_CREDENTIALS .env
```

**Opciones**:
- **A**: Configurar credenciales correctamente
- **B**: Deshabilitar Vision API (más rápido)

---

### 3. Permisos de Archivos

**Síntoma**: Error al guardar imágenes

**Verificar**:
```bash
ls -la media/
```

**Corregir**:
```bash
sudo chown -R $USER:$USER media/
chmod -R 755 media/
```

---

## 🛠 Comandos Útiles

### Diagnóstico

```bash
# Diagnóstico completo (recomendado)
bash check_config.sh

# Diagnóstico Django
python manage.py check_production_config

# System checks
python manage.py check --deploy
```

### Verificación

```bash
# Ver Site actual
python manage.py shell -c "from django.contrib.sites.models import Site; s=Site.objects.get(id=1); print(f'ID: {s.id}, Domain: {s.domain}, Name: {s.name}')"

# Ver SocialApps
python manage.py shell -c "from allauth.socialaccount.models import SocialApp; [print(f'{a.provider}: Sites={[s.domain for s in a.sites.all()]}') for a in SocialApp.objects.all()]"

# Ver configuración de Vision API
grep -E "(GOOGLE_VISION|GOOGLE_APPLICATION)" .env
```

### Logs

```bash
# Ver logs en tiempo real
tail -f /var/log/nginx/error.log

# Logs de Django (si están configurados)
tail -f /var/log/django/app.log

# Logs de Docker
docker-compose logs -f web
```

---

## 📞 Flujo de Resolución

```
┌─────────────────────────────────┐
│  Error 500 en Producción        │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│  bash check_config.sh           │
│  (Diagnóstico automático)       │
└────────────┬────────────────────┘
             │
             ▼
      ┌──────┴──────┐
      │             │
      ▼             ▼
┌─────────┐   ┌─────────────┐
│ Google  │   │  Subida de  │
│ OAuth   │   │  Imágenes   │
└────┬────┘   └──────┬──────┘
     │               │
     ▼               ▼
┌─────────┐   ┌─────────────┐
│ Corregir│   │ Deshabilitar│
│  Site   │   │  Vision API │
└────┬────┘   └──────┬──────┘
     │               │
     └───────┬───────┘
             │
             ▼
┌─────────────────────────────────┐
│  Probar en Navegador            │
│  (Modo incógnito)               │
└────────────┬────────────────────┘
             │
             ▼
        ┌────┴────┐
        │         │
        ▼         ▼
    ┌───────┐ ┌───────┐
    │  ✅   │ │  ❌   │
    │ Listo │ │ Logs  │
    └───────┘ └───┬───┘
                  │
                  ▼
          ┌───────────────┐
          │ Ver logs      │
          │ detallados    │
          └───────────────┘
```

---

## ✅ Checklist de Verificación

Antes de dar por resuelto:

- [ ] Ejecuté `bash check_config.sh`
- [ ] No hay errores en el diagnóstico
- [ ] Site.domain es correcto
- [ ] SocialApp tiene el Site asociado
- [ ] Login con Google funciona
- [ ] Subida de imágenes funciona
- [ ] Logs se están generando correctamente
- [ ] DEBUG=False en producción

---

## 🎯 Resumen de Causas

### Login con Google (Error 500)

| Probabilidad | Causa | Solución |
|--------------|-------|----------|
| 90% | Site.domain incorrecto | Actualizar en BD |
| 8% | SocialApp sin Site | Asociar en admin |
| 2% | URIs no autorizados | Configurar en Google Cloud |

### Subida de Imágenes (Error 500)

| Probabilidad | Causa | Solución |
|--------------|-------|----------|
| 80% | Credenciales Vision API | Configurar o deshabilitar |
| 15% | Permisos de media/ | chmod/chown |
| 5% | Cuota API excedida | Revisar Google Cloud |

---

## 🆘 ¿Aún No Funciona?

1. **Habilita DEBUG temporalmente** (solo para diagnosticar):
   ```bash
   # En .env
   DEBUG=True
   # Reiniciar
   # Ver error completo en navegador
   # IMPORTANTE: Volver a DEBUG=False después
   ```

2. **Revisa logs detallados**:
   ```bash
   tail -100 /var/log/nginx/error.log
   ```

3. **Ejecuta diagnóstico completo**:
   ```bash
   python manage.py check_production_config
   ```

4. **Comparte información**:
   - Output de `check_config.sh`
   - Últimas 50 líneas de logs
   - Mensaje de error exacto

---

## 📖 Documentación Adicional

- **Django Sites Framework**: https://docs.djangoproject.com/en/5.2/ref/contrib/sites/
- **django-allauth**: https://docs.allauth.org/en/latest/
- **Google Vision API**: https://cloud.google.com/vision/docs
- **Google OAuth Setup**: https://console.cloud.google.com/apis/credentials

---

## 🎓 Prevención Futura

### Añadir a tu proceso de deploy:

```bash
#!/bin/bash
# deploy.sh

# 1. Verificar configuración
python manage.py check --deploy

# 2. Verificar configuración de producción
python manage.py check_production_config

# 3. Si todo OK, continuar con deploy
# ...
```

### Monitoreo continuo:

- Configurar Sentry para tracking de errores
- Logs centralizados (ELK, Loki, etc.)
- Alertas automáticas por email/Slack

---

**¿Listo para empezar?** → Ejecuta `bash check_config.sh` 🚀