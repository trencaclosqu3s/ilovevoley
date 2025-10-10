# 📧 Sistema de Notificaciones por Email

Este documento explica cómo configurar y usar el sistema de notificaciones por email implementado en I Love Voley.

## ✨ Funcionalidades Implementadas

### 1. 👤 Notificaciones de Usuarios
- **Nuevo usuario pendiente**: Email a admins cuando alguien se registra
- **Usuario aprobado**: Email al usuario cuando es aprobado por un admin

### 2. 📸 Notificaciones de Imágenes
- **Imagen pendiente**: Email a admins cuando se sube una imagen nueva
- **Imagen moderada**: Email al usuario cuando su imagen es aprobada/rechazada

### 3. 🔍 Notificaciones de Errores 404
- **Reporte diario**: Resumen diario de errores 404
- **Alerta inmediata**: Email cuando hay muchos 404s en poco tiempo

## ⚙️ Configuración

### 1. Variables de Entorno

Copia `.env.example` a `.env` y configura las siguientes variables:

```bash
# Configuración básica de email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=tu-email@gmail.com
EMAIL_HOST_PASSWORD=tu-app-password
DEFAULT_FROM_EMAIL=tu-email@gmail.com

# Sistema de notificaciones
NOTIFICATION_EMAIL_ENABLED=True

# ADMIN_EMAIL_LIST ya NO es necesario - Los emails se envían automáticamente 
# a todos los usuarios superuser que tengan email configurado en la base de datos.
# Esto hace el sistema más dinámico y evita tener que mantener listas manuales.

# (OPCIONAL) Solo si quieres un fallback cuando no hay superusers con email:
# ADMIN_EMAIL_LIST=admin1@example.com,admin2@example.com

# Configuración específica (True/False)
EMAIL_NOTIFY_NEW_USER=True
EMAIL_NOTIFY_USER_APPROVED=True
EMAIL_NOTIFY_IMAGE_PENDING=True
EMAIL_NOTIFY_IMAGE_MODERATED=True
EMAIL_NOTIFY_404_DAILY=False
```

### 2. Configuración de Gmail

Para usar Gmail necesitas:

1. **Habilitar autenticación de 2 factores** en tu cuenta de Google
2. **Generar una contraseña de aplicación**:
   - Ve a https://myaccount.google.com/
   - Seguridad → Contraseñas de aplicaciones
   - Genera una contraseña para "Otra aplicación"
   - Usa esa contraseña en `EMAIL_HOST_PASSWORD`

### 3. Otros Proveedores de Email

```bash
# SendGrid
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=tu-api-key-de-sendgrid

# Mailgun
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_HOST_USER=tu-usuario@tu-dominio.mailgun.org
EMAIL_HOST_PASSWORD=tu-password-mailgun

# Outlook/Hotmail
EMAIL_HOST=smtp-mail.outlook.com
EMAIL_PORT=587
EMAIL_HOST_USER=tu-email@outlook.com
EMAIL_HOST_PASSWORD=tu-password
```

## 🧪 Pruebas

### Comando de Prueba

```bash
# Verificar configuración
docker-compose exec web python manage.py test_email_notifications --test-type=config

# Probar todas las notificaciones
docker-compose exec web python manage.py test_email_notifications --test-type=all

# Probar tipo específico
docker-compose exec web python manage.py test_email_notifications --test-type=user
docker-compose exec web python manage.py test_email_notifications --test-type=image
docker-compose exec web python manage.py test_email_notifications --test-type=404

# Enviar a email específico
docker-compose exec web python manage.py test_email_notifications --test-type=all --email=tu-email@example.com
```

### Prueba Rápida

```bash
# Probar envío básico
docker-compose exec web python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

send_mail(
    'Prueba',
    'Email de prueba',
    settings.DEFAULT_FROM_EMAIL,
    ['tu-email@example.com'],
    fail_silently=False
)
```

## 🎯 Uso del Sistema

### ⚡ Sistema Dinámico de Destinatarios

**¡IMPORTANTE!** Los emails a administradores se envían automáticamente a todos los **usuarios superuser** que tengan email configurado en la base de datos.

**Ventajas:**
- ✅ No necesitas mantener listas manuales de emails
- ✅ Cuando añades/quitas admins, los emails se actualizan automáticamente
- ✅ Gestión centralizada desde el panel de Django Admin

**Para recibir emails de notificaciones:**
1. El usuario debe ser **superuser** (`is_superuser=True`)
2. El usuario debe tener un **email configurado** en su perfil

**Comprobar superusers con email:**
```bash
docker-compose exec web python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.filter(is_superuser=True, email__isnull=False).exclude(email='').values('username', 'email')
```

### Activación/Desactivación

- **Global**: `NOTIFICATION_EMAIL_ENABLED=True/False`
- **Por tipo**: Variables `EMAIL_NOTIFY_*` individuales

### Triggers Automáticos

1. **Usuario se registra** → Email a todos los superusers
2. **Admin aprueba usuario** → Email al usuario
3. **Usuario sube imagen** → Email a todos los superusers
4. **Admin modera imagen** → Email al usuario
5. **10+ errores 404 en 1 hora** → Alerta inmediata a superusers
6. **Reporte diario 404** → Cron job (configurar por separado)

## 📋 Configuración de Reporte Diario 404

Para el reporte diario, añade a tu crontab:

```bash
# Editar crontab
crontab -e

# Añadir línea (envía reporte a las 8:00 AM todos los días)
0 8 * * * /usr/bin/docker-compose -f /ruta/a/tu/proyecto/docker-compose.yml exec -T web python manage.py shell -c "from videosvoley.core.middleware import send_404_daily_report; send_404_daily_report()"
```

O usando Django-Q/Celery si los tienes configurados.

## 🎨 Personalización de Templates

Los templates están en `videosvoley/templates/emails/`:

- `base_email.html` - Template base con estilos
- `new_user_pending.html` - Usuario pendiente
- `user_approved.html` - Usuario aprobado
- `image_pending.html` - Imagen pendiente
- `image_approved.html` - Imagen aprobada
- `image_rejected.html` - Imagen rechazada
- `404_daily_report.html` - Reporte diario 404
- `404_alert.html` - Alerta inmediata 404

### Personalizar Estilos

Edita `base_email.html` para cambiar:
- Colores corporativos
- Logo de la aplicación
- Pie de página
- Estilos CSS

## 🚨 Troubleshooting

### Email no se envía

1. **Verificar configuración**:
   ```bash
   docker-compose exec web python manage.py test_email_notifications --test-type=config
   ```

2. **Revisar logs**:
   ```bash
   docker-compose logs web | grep -i email
   ```

3. **Problemas comunes**:
   - Contraseña de aplicación incorrecta (Gmail)
   - Puerto bloqueado por firewall
   - `NOTIFICATION_EMAIL_ENABLED=False`
   - No hay superusers con email configurado

### Email va a spam

- Configura SPF, DKIM y DMARC en tu dominio
- Usa un dominio verificado como remitente
- Evita palabras spam en asuntos

### Templates no se cargan

- Verificar que `videosvoley/templates` está en `TEMPLATES.DIRS`
- Comprobar permisos de archivos
- Revisar sintaxis de templates Django

## 📊 Monitoreo

### Logs de Email

Los emails registran en stdout:
```
Email enviado: Nuevo usuario pendiente a admin@example.com
Error enviando email: SMTP Error - Authentication failed
```

### Estadísticas

Para ver estadísticas de emails enviados, puedes crear un modelo de log personalizado o usar herramientas como:
- SendGrid Analytics
- Mailgun Logs
- Google Analytics (para links en emails)

## 🔧 Desarrollo

### Añadir Nueva Notificación

1. **Crear signal** en `signals.py`:
   ```python
   @receiver(post_save, sender=MiModelo)
   def mi_notificacion(sender, instance, created, **kwargs):
       if created:
           send_notification_email(
               subject='Mi notificación',
               template_name='emails/mi_template.html',
               context={'objeto': instance}
           )
   ```

2. **Crear template** en `emails/mi_template.html`

3. **Añadir configuración** en `settings.py`:
   ```python
   EMAIL_NOTIFICATIONS = {
       # ... existentes ...
       'mi_nueva_notificacion': env_config('EMAIL_NOTIFY_MI_NOTIF', default=True, cast=bool),
   }
   ```

4. **Añadir variable** en `.env.example`

### Testing

Usa el comando de prueba durante desarrollo:
```bash
docker-compose exec web python manage.py test_email_notifications --test-type=all --email=tu-email-dev@example.com
```

## 📚 Referencias

- [Django Email](https://docs.djangoproject.com/en/5.2/topics/email/)
- [Django Signals](https://docs.djangoproject.com/en/5.2/topics/signals/)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [HTML Email Best Practices](https://www.campaignmonitor.com/dev-resources/guides/html-email-guide/)

---

**💡 Tip**: Empieza con notificaciones críticas (usuarios pendientes) y ve añadiendo gradualmente otras según necesites.