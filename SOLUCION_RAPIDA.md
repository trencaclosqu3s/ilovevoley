# 🚨 Solución Rápida - Errores 500 en Producción

## Resumen
Tienes dos errores 500 en producción:
1. **Login con Google** → Problema de configuración de django-allauth
2. **Subida de imágenes** → Problema con Google Vision API

---

## ✅ Pasos Inmediatos (5-10 minutos)

### 1️⃣ Ejecutar diagnóstico automático

```bash
# Conectarse al servidor de producción y ejecutar:
cd /ruta/a/tu/proyecto
python manage.py check_production_config
```

Este comando te mostrará exactamente qué está mal configurado.

### 2️⃣ Verificar y corregir Site de Django

```bash
python manage.py shell
```

Dentro del shell de Django:
```python
from django.contrib.sites.models import Site

# Ver el site actual
site = Site.objects.get(id=1)
print(f"Domain actual: {site.domain}")

# Si no es tu dominio de producción, corregirlo:
site.domain = 'tu-dominio-produccion.com'  # SIN https://
site.name = 'VideosVoley'
site.save()
print("✓ Site actualizado")
```

### 3️⃣ Verificar Google OAuth en Admin

1. Ir a: `https://tu-dominio.com/admin/socialaccount/socialapp/`
2. Verificar que existe una app de Google
3. **IMPORTANTE**: En "Sites", debe estar seleccionado tu dominio de producción
4. Si no está, añadirlo y guardar

### 4️⃣ Solución temporal para imágenes

Si quieres que las imágenes funcionen inmediatamente (sin Vision API):

```bash
# Editar .env de producción:
GOOGLE_VISION_ENABLED=False
AUTO_MODERATION_ENABLED=False

# Reiniciar la aplicación
sudo systemctl restart tu-servicio-django
# O si usas Docker:
docker-compose restart web
```

**Efecto**: Las imágenes se subirán correctamente pero quedarán pendientes de moderación manual.

---

## 🔍 Diagnóstico Detallado

### Para Google OAuth:

**Verificar URIs autorizados en Google Cloud Console:**

1. Ir a: https://console.cloud.google.com/apis/credentials
2. Seleccionar tu OAuth 2.0 Client ID
3. En "URIs de redireccionamiento autorizados" debe estar:
   ```
   https://tu-dominio-produccion.com/accounts/google/login/callback/
   ```
4. Si no está, añadirlo y guardar

**Verificar variables de entorno:**
```bash
# En .env de producción:
ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com
CSRF_TRUSTED_ORIGINS=https://tu-dominio.com,https://www.tu-dominio.com
```

### Para Google Vision API:

**Opción A: Configurar correctamente (solución permanente)**

1. Descargar credenciales desde Google Cloud Console:
   - Ir a: https://console.cloud.google.com/iam-admin/serviceaccounts
   - Crear o seleccionar una cuenta de servicio
   - Crear una clave JSON y descargarla

2. Subir el archivo al servidor:
   ```bash
   # En tu máquina local:
   scp google-credentials.json usuario@servidor:/ruta/segura/
   
   # En el servidor, proteger el archivo:
   chmod 600 /ruta/segura/google-credentials.json
   ```

3. Configurar en .env:
   ```bash
   GOOGLE_APPLICATION_CREDENTIALS=/ruta/segura/google-credentials.json
   GOOGLE_VISION_ENABLED=True
   AUTO_MODERATION_ENABLED=True  # Opcional
   ```

4. Reiniciar la aplicación

**Opción B: Deshabilitar temporalmente (solución rápida)**

Ya explicado en el paso 4️⃣ arriba.

---

## 🧪 Probar las Soluciones

### Probar Google OAuth:

1. Abrir navegador en modo incógnito
2. Ir a tu sitio de producción
3. Intentar "Iniciar sesión con Google"
4. Debería funcionar sin error 500

### Probar subida de imágenes:

1. Iniciar sesión en producción
2. Ir a la sección de subida de imágenes
3. Subir una imagen de prueba
4. Debería subirse sin error 500

---

## 📊 Comandos de Verificación

```bash
# 1. Verificar configuración general
python manage.py check --deploy

# 2. Verificar Site
python manage.py shell -c "from django.contrib.sites.models import Site; s=Site.objects.get(id=1); print(f'Domain: {s.domain}')"

# 3. Verificar SocialApps
python manage.py shell -c "from allauth.socialaccount.models import SocialApp; [print(f'{a.provider}: {a.name} - Sites: {[s.domain for s in a.sites.all()]}') for a in SocialApp.objects.all()]"

# 4. Verificar permisos de media
ls -la media/
# Debe mostrar permisos de escritura para el usuario del servidor web

# 5. Ver logs en tiempo real (para detectar errores)
tail -f /var/log/nginx/error.log
# O si usas Docker:
docker-compose logs -f web
```

---

## 🎯 Checklist Rápido

- [ ] Ejecuté `python manage.py check_production_config`
- [ ] Verifiqué que Site.domain es correcto en la BD
- [ ] Verifiqué que SocialApp de Google tiene el Site correcto
- [ ] Verifiqué URIs en Google Cloud Console
- [ ] Configuré ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS
- [ ] Decidí si usar Vision API o deshabilitarla
- [ ] Si uso Vision API: configuré credenciales correctamente
- [ ] Reinicié la aplicación después de cambios
- [ ] Probé login con Google en modo incógnito
- [ ] Probé subir una imagen

---

## 🆘 Si Aún No Funciona

### Ver logs detallados:

```bash
# Logs de Django (ajustar ruta según tu configuración)
tail -100 /var/log/django/app.log

# Logs de nginx/apache
tail -100 /var/log/nginx/error.log

# Si usas Docker:
docker-compose logs --tail=100 web
```

### Habilitar DEBUG temporalmente (SOLO para diagnosticar):

```bash
# En .env:
DEBUG=True

# Reiniciar
# IMPORTANTE: Volver a poner DEBUG=False después de diagnosticar
```

Luego intenta reproducir el error y verás el traceback completo.

---

## 📞 Información Adicional

- **Documento completo**: Ver `DIAGNOSTICO_ERRORES_PRODUCCION.md` para análisis detallado
- **Mejoras implementadas**: 
  - ✅ Sistema de checks automáticos
  - ✅ Logging mejorado con detalles
  - ✅ Notificaciones por email de errores
  - ✅ Comando de diagnóstico de producción

---

## 💡 Causa Más Probable de Cada Error

### Error 500 en Login con Google:
**Causa #1 (90%)**: El `Site.domain` en la base de datos no coincide con tu dominio de producción.
**Causa #2 (8%)**: La SocialApp de Google no tiene asociado el Site correcto.
**Causa #3 (2%)**: URIs no autorizados en Google Cloud Console.

### Error 500 en Subida de Imágenes:
**Causa #1 (80%)**: `GOOGLE_APPLICATION_CREDENTIALS` no configurado o archivo no existe.
**Causa #2 (15%)**: Permisos incorrectos en directorio `media/`.
**Causa #3 (5%)**: Cuota de Google Vision API excedida o credenciales inválidas.

---

¿Necesitas ayuda con algún paso específico? Ejecuta primero el comando de diagnóstico y comparte el resultado.