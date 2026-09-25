# Diagnóstico de Errores 500 en Producción

## Resumen
Se detectan dos problemas que causan error 500 en producción pero funcionan correctamente en local:
1. **Login con Google OAuth** - Error 500 al intentar autenticarse
2. **Subida de imágenes** - Error 500 al subir fotos (proceso de moderación con Google Vision API)

---

## 🔴 Problema 1: Login con Google OAuth

### Síntomas
- Error 500 al intentar hacer login con Google
- Funciona correctamente en local
- El error ocurre durante el proceso de autenticación de django-allauth

### Causas Probables

#### 1. **SITE_ID incorrecto o no configurado en producción** ⚠️ MUY PROBABLE
```python
# En config/settings.py
SITE_ID = 1
```

**Problema**: Django Sites Framework requiere que el `SITE_ID` coincida con el dominio configurado en la base de datos.

**Solución**:
```bash
# Conectarse a la base de datos de producción y verificar:
python manage.py shell

from django.contrib.sites.models import Site
site = Site.objects.get_current()
print(f"Site ID: {site.id}, Domain: {site.domain}, Name: {site.name}")

# Si el dominio no es correcto, actualizarlo:
site = Site.objects.get(id=1)
site.domain = 'tu-dominio-produccion.com'  # Sin https://
site.name = 'I Love Voley'
site.save()
```

#### 2. **Credenciales de Google OAuth no configuradas correctamente** ⚠️ PROBABLE
Las credenciales de Google OAuth (Client ID y Secret) deben estar configuradas en el admin de Django para el dominio de producción.

**Verificar**:
1. Ir al admin de Django: `/admin/socialaccount/socialapp/`
2. Verificar que existe una aplicación de Google configurada
3. Verificar que el **Client ID** y **Client Secret** son correctos
4. **CRÍTICO**: Verificar que el dominio de producción está en la lista de "Sites" de la aplicación

**URIs de redirección autorizados en Google Cloud Console**:
```
https://tu-dominio-produccion.com/accounts/google/login/callback/
```

#### 3. **ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS** ⚠️ PROBABLE
```python
# Verificar en .env de producción:
ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com
CSRF_TRUSTED_ORIGINS=https://tu-dominio.com,https://www.tu-dominio.com
```

#### 4. **Middleware AccountMiddleware** ✅ YA CONFIGURADO
El middleware `allauth.account.middleware.AccountMiddleware` está correctamente configurado en línea 104 de `config/settings.py`.

---

## 🔴 Problema 2: Subida de Imágenes (Google Vision API)

### Síntomas
- Error 500 al intentar subir una foto
- El proceso incluye moderación automática con Google Vision API
- Funciona correctamente en local

### Causas Probables

#### 1. **Credenciales de Google Vision API no configuradas** ⚠️ MUY PROBABLE

**Problema**: La variable de entorno `GOOGLE_APPLICATION_CREDENTIALS` no está configurada o apunta a un archivo inexistente en producción.

**Código afectado** (`ilovevoley/videos/utils.py:36-39`):
```python
from google.cloud import vision
client = vision.ImageAnnotatorClient()  # ← Falla aquí si no hay credenciales
```

**Soluciones**:

##### Opción A: Usar archivo de credenciales JSON
```bash
# 1. Descargar las credenciales desde Google Cloud Console
# 2. Subir el archivo al servidor de producción en una ubicación segura
# 3. Configurar en .env:
GOOGLE_APPLICATION_CREDENTIALS=/ruta/segura/credentials.json
GOOGLE_VISION_ENABLED=True
```

##### Opción B: Usar variables de entorno (recomendado para Docker/Cloud)
```python
# En config/settings.py, añadir:
import os
import json

# Configurar credenciales desde variable de entorno
GOOGLE_CREDENTIALS_JSON = env_config('GOOGLE_CREDENTIALS_JSON', default='')
if GOOGLE_CREDENTIALS_JSON and GOOGLE_VISION_ENABLED:
    # Escribir credenciales temporalmente (útil para Docker)
    credentials_path = '/tmp/google-credentials.json'
    with open(credentials_path, 'w') as f:
        f.write(GOOGLE_CREDENTIALS_JSON)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
```

##### Opción C: Deshabilitar temporalmente Google Vision
```bash
# En .env de producción:
GOOGLE_VISION_ENABLED=False
AUTO_MODERATION_ENABLED=False
```

Esto permitirá que las imágenes se suban pero quedarán pendientes de moderación manual.

#### 2. **Permisos de archivos/directorios** ⚠️ POSIBLE

**Problema**: El servidor web no tiene permisos para escribir en el directorio `MEDIA_ROOT`.

**Verificar**:
```bash
# En el servidor de producción:
ls -la /ruta/a/media/
# El usuario del servidor web (ej: www-data, nginx) debe tener permisos de escritura

# Corregir permisos:
sudo chown -R www-data:www-data /ruta/a/media/
sudo chmod -R 755 /ruta/a/media/
```

#### 3. **Manejo de excepciones silencioso** ⚠️ DETECTADO

**Problema**: El código tiene un `try-except` que captura excepciones pero solo las imprime con `print()`, lo cual no se registra en logs de producción.

**Código actual** (`ilovevoley/videos/views.py:658-663`):
```python
except Exception as e:
    # Log error y marcar como que requiere revisión manual
    print(f"Error en Vision API: {e}")  # ← No se verá en producción
    image.vision_api_checked = False
    image.vision_api_safe = False
    image.vision_api_details = {'error': str(e), 'api_response_ok': False}
```

**Solución**: Usar logging adecuado (ver sección de mejoras).

---

## 🔧 Soluciones Inmediatas

### Para Google OAuth:

1. **Verificar y corregir Site en base de datos**:
```python
python manage.py shell

from django.contrib.sites.models import Site
site = Site.objects.get(id=1)
site.domain = 'tu-dominio-produccion.com'
site.name = 'I Love Voley'
site.save()
```

2. **Verificar SocialApp en admin**:
   - Ir a `/admin/socialaccount/socialapp/`
   - Verificar que existe la app de Google
   - Verificar que el Site de producción está seleccionado
   - Verificar Client ID y Secret

3. **Verificar URIs en Google Cloud Console**:
   - Ir a https://console.cloud.google.com/apis/credentials
   - Verificar que la URI de callback está autorizada:
     `https://tu-dominio.com/accounts/google/login/callback/`

### Para Google Vision API:

1. **Opción rápida - Deshabilitar temporalmente**:
```bash
# En .env de producción:
GOOGLE_VISION_ENABLED=False
AUTO_MODERATION_ENABLED=False
```

2. **Opción permanente - Configurar credenciales**:
```bash
# Descargar credenciales de Google Cloud Console
# Subir al servidor y configurar:
GOOGLE_APPLICATION_CREDENTIALS=/ruta/segura/google-credentials.json
GOOGLE_VISION_ENABLED=True
```

---

## 🚀 Mejoras Recomendadas

### 1. Añadir logging adecuado

Crear archivo `ilovevoley/core/logging_config.py`:
```python
import logging

def get_logger(name):
    """Obtener logger configurado"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

### 2. Mejorar manejo de errores en views.py

```python
import logging
logger = logging.getLogger(__name__)

# En image_upload view, reemplazar:
except Exception as e:
    print(f"Error en Vision API: {e}")
    
# Por:
except Exception as e:
    logger.error(f"Error en Vision API al procesar imagen: {e}", exc_info=True)
    # También enviar email a admins si es crítico
    if settings.DEBUG:
        raise  # Re-lanzar en desarrollo para ver el traceback completo
```

### 3. Añadir validación de configuración al inicio

Crear `ilovevoley/core/checks.py`:
```python
from django.core.checks import Warning, register, Tags
from django.conf import settings
import os

@register(Tags.compatibility)
def check_google_vision_config(app_configs, **kwargs):
    warnings = []
    
    if settings.GOOGLE_VISION_ENABLED:
        creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if not creds_path or not os.path.exists(creds_path):
            warnings.append(
                Warning(
                    'Google Vision API está habilitada pero las credenciales no están configuradas correctamente',
                    hint='Configure GOOGLE_APPLICATION_CREDENTIALS en .env',
                    id='ilovevoley.W001',
                )
            )
    
    return warnings

@register(Tags.compatibility)
def check_socialauth_config(app_configs, **kwargs):
    warnings = []
    
    from django.contrib.sites.models import Site
    try:
        site = Site.objects.get(id=settings.SITE_ID)
        if site.domain in ['example.com', 'localhost']:
            warnings.append(
                Warning(
                    f'Site domain está configurado como "{site.domain}" - actualizar para producción',
                    hint='Ejecutar: python manage.py shell y actualizar Site.objects.get(id=1)',
                    id='ilovevoley.W002',
                )
            )
    except Site.DoesNotExist:
        warnings.append(
            Warning(
                f'Site con ID {settings.SITE_ID} no existe en la base de datos',
                hint='Ejecutar: python manage.py migrate',
                id='ilovevoley.W003',
            )
        )
    
    return warnings
```

### 4. Añadir comando de diagnóstico

Crear `ilovevoley/core/management/commands/check_production_config.py`:
```python
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sites.models import Site
import os

class Command(BaseCommand):
    help = 'Verifica la configuración de producción'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Verificación de Configuración de Producción ===\n'))
        
        # 1. Verificar Site
        try:
            site = Site.objects.get(id=settings.SITE_ID)
            self.stdout.write(f'✓ Site ID: {site.id}')
            self.stdout.write(f'  Domain: {site.domain}')
            self.stdout.write(f'  Name: {site.name}')
            
            if site.domain in ['example.com', 'localhost', '127.0.0.1']:
                self.stdout.write(self.style.WARNING(f'  ⚠ ADVERTENCIA: Domain parece ser de desarrollo'))
        except Site.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ Site con ID {settings.SITE_ID} no existe'))
        
        # 2. Verificar Google OAuth
        from allauth.socialaccount.models import SocialApp
        google_apps = SocialApp.objects.filter(provider='google')
        if google_apps.exists():
            for app in google_apps:
                self.stdout.write(f'\n✓ Google OAuth App: {app.name}')
                self.stdout.write(f'  Client ID: {app.client_id[:20]}...')
                self.stdout.write(f'  Sites: {", ".join([s.domain for s in app.sites.all()])}')
                
                if not app.sites.filter(id=settings.SITE_ID).exists():
                    self.stdout.write(self.style.WARNING(f'  ⚠ ADVERTENCIA: Site actual no está asociado'))
        else:
            self.stdout.write(self.style.WARNING('\n⚠ No hay apps de Google OAuth configuradas'))
        
        # 3. Verificar Google Vision
        self.stdout.write(f'\n{"✓" if settings.GOOGLE_VISION_ENABLED else "✗"} Google Vision: {"Habilitada" if settings.GOOGLE_VISION_ENABLED else "Deshabilitada"}')
        if settings.GOOGLE_VISION_ENABLED:
            creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
            if creds_path and os.path.exists(creds_path):
                self.stdout.write(f'  ✓ Credenciales: {creds_path}')
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ Credenciales no encontradas: {creds_path}'))
        
        # 4. Verificar permisos de media
        media_root = settings.MEDIA_ROOT
        if os.path.exists(media_root):
            self.stdout.write(f'\n✓ MEDIA_ROOT existe: {media_root}')
            if os.access(media_root, os.W_OK):
                self.stdout.write(f'  ✓ Permisos de escritura: OK')
            else:
                self.stdout.write(self.style.ERROR(f'  ✗ Sin permisos de escritura'))
        else:
            self.stdout.write(self.style.ERROR(f'\n✗ MEDIA_ROOT no existe: {media_root}'))
        
        # 5. Verificar configuración de email
        self.stdout.write(f'\n{"✓" if settings.NOTIFICATION_EMAIL_ENABLED else "✗"} Notificaciones email: {"Habilitadas" if settings.NOTIFICATION_EMAIL_ENABLED else "Deshabilitadas"}')
        if settings.NOTIFICATION_EMAIL_ENABLED:
            self.stdout.write(f'  Email host: {settings.EMAIL_HOST}')
            self.stdout.write(f'  Admins: {len(settings.ADMIN_EMAIL_LIST)} configurados')
        
        self.stdout.write(self.style.SUCCESS('\n=== Fin de verificación ==='))
```

---

## 📋 Checklist de Verificación

### Google OAuth:
- [ ] Verificar `SITE_ID` en settings.py
- [ ] Verificar dominio en tabla `django_site` de la BD
- [ ] Verificar SocialApp en admin Django
- [ ] Verificar URIs autorizados en Google Cloud Console
- [ ] Verificar `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`

### Google Vision API:
- [ ] Verificar `GOOGLE_VISION_ENABLED` en .env
- [ ] Verificar `GOOGLE_APPLICATION_CREDENTIALS` existe y es accesible
- [ ] Verificar permisos del directorio MEDIA_ROOT
- [ ] Verificar que google-cloud-vision está instalado
- [ ] Revisar logs del servidor para ver el error exacto

### General:
- [ ] Ejecutar `python manage.py check` en producción
- [ ] Ejecutar `python manage.py check_production_config` (después de crear el comando)
- [ ] Revisar logs del servidor web (nginx/apache)
- [ ] Revisar logs de la aplicación Django
- [ ] Verificar que todas las migraciones están aplicadas

---

## 🔍 Comandos de Diagnóstico

```bash
# En el servidor de producción:

# 1. Verificar configuración de Django
python manage.py check --deploy

# 2. Verificar Site
python manage.py shell -c "from django.contrib.sites.models import Site; print(Site.objects.get(id=1))"

# 3. Verificar SocialApps
python manage.py shell -c "from allauth.socialaccount.models import SocialApp; [print(f'{app.provider}: {app.name}') for app in SocialApp.objects.all()]"

# 4. Verificar permisos de media
ls -la media/

# 5. Probar Google Vision API
python manage.py shell
>>> from ilovevoley.videos.utils import check_image_with_vision_api
>>> # Intentar cargar una imagen de prueba

# 6. Ver logs en tiempo real
tail -f /var/log/nginx/error.log
tail -f /path/to/django/logs/app.log
```

---

## 📞 Próximos Pasos

1. **Inmediato**: Ejecutar los comandos de diagnóstico para identificar el problema exacto
2. **Corto plazo**: Implementar las soluciones inmediatas según el diagnóstico
3. **Medio plazo**: Implementar las mejoras de logging y validación
4. **Largo plazo**: Añadir monitoreo y alertas automáticas

¿Necesitas ayuda para ejecutar alguno de estos pasos?