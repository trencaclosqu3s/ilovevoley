# 📧 Sistema de Notificaciones por Email

Este documento explica cómo configurar y usar el sistema de notificaciones por email implementado en I Love Voley.

## ✨ Funcionalidades Implementadas

### 1. 👤 Notificaciones de Usuarios
- **Nuevo usuario / membresía pendiente**: Email a los moderadores cuando alguien se registra o solicita unirse a un club
- **Usuario aprobado / rechazado**: Email al usuario con el resultado de la moderación
- **Reactivación pendiente** y **aviso de inactividad** (#327)

### 2. 📸 Notificaciones de Imágenes
- **Imagen pendiente**: Email a los moderadores cuando se sube una imagen nueva (agrupado por lote en subidas múltiples)
- **Imagen moderada**: Email al usuario cuando su imagen es aprobada/rechazada
- **Error de Google Vision**: Aviso técnico si falla el análisis de la imagen

### 3. 🔍 Notificaciones de Errores 404
- **Reporte diario**: Resumen diario de errores 404
- **Alerta inmediata**: Email cuando hay muchos 404s en poco tiempo

### 4. 🗂️ Otras
- **Vínculo cuenta ↔ ficha** aprobado/rechazado (#531), **Season Wrapped** y novedades de temporada a jugadores y familias
- **Ligas o identidades de equipo pendientes de validar** (a superusers, #377 / #428)
- **Mensaje directo del admin** a usuarios (`send_admin_email_to_users`)

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

# Sistema de notificaciones (por defecto False: sin él no sale ningún aviso)
NOTIFICATION_EMAIL_ENABLED=True

# ADMIN_EMAIL_LIST ya NO es necesario - Los emails se envían automáticamente 
# a todos los usuarios superuser que tengan email configurado en la base de datos.
# Esto hace el sistema más dinámico y evita tener que mantener listas manuales.

# (OPCIONAL) Solo si quieres un fallback cuando no hay superusers con email:
# ADMIN_EMAIL_LIST=admin1@example.com,admin2@example.com

# (OPCIONAL) Destinatarios de avisos técnicos (alertas/reporte de errores 404).
# No se envían a todos los superusers: un superuser puede existir solo para
# gestionar contenido. Prioridad: TECHNICAL_ALERT_EMAILS > ADMIN_EMAIL_LIST > superusers.
# TECHNICAL_ALERT_EMAILS=tecnico@example.com

# Configuración específica (True/False)
EMAIL_NOTIFY_NEW_USER=True
EMAIL_NOTIFY_USER_APPROVED=True
EMAIL_NOTIFY_IMAGE_PENDING=True
EMAIL_NOTIFY_IMAGE_MODERATED=True
EMAIL_NOTIFY_404_DAILY=False
EMAIL_NOTIFY_USER_INACTIVITY=False
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
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=config

# Probar todas las notificaciones
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=all

# Probar tipo específico
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=user
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=image
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=404

# Enviar a email específico
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=all --email=tu-email@example.com
```

### Prueba Rápida

```bash
# Probar envío básico
docker compose -f docker-compose.dev.yml run --rm web python manage.py shell
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

**¡IMPORTANTE!** Los avisos de moderación (`get_moderation_recipients` en `ilovevoley/core/email_utils.py`) se envían automáticamente a todos los **usuarios superuser** con email y, cuando hay tenant, a los **managers/admins aprobados** de esa organización. Los avisos técnicos (404) usan `get_technical_alert_emails()` (`TECHNICAL_ALERT_EMAILS` > `ADMIN_EMAIL_LIST` > superusers).

**Ventajas:**
- ✅ No necesitas mantener listas manuales de emails
- ✅ Cuando añades/quitas admins, los emails se actualizan automáticamente
- ✅ Gestión centralizada desde el panel de Django Admin

**Para recibir emails de moderación:**
1. El usuario debe ser **superuser** (`is_superuser=True`) o **manager/admin** aprobado del club
2. El usuario debe tener un **email configurado** en su perfil

**Comprobar superusers con email:**
```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.filter(is_superuser=True, email__isnull=False).exclude(email='').values('username', 'email')
```

### Activación/Desactivación

- **Global**: `NOTIFICATION_EMAIL_ENABLED=True/False`
- **Por tipo**: Variables `EMAIL_NOTIFY_*` individuales

### Triggers Automáticos

Se encolan como tareas Celery en `ilovevoley/core/tasks.py` (`notify_new_user_pending`, `notify_membership_pending`, `notify_image_pending`, `notify_images_pending_batch`, `notify_user_moderation_result`, `notify_image_moderation_result`, `send_404_immediate_alert`...):

1. **Usuario se registra o solicita unirse a un club** → Email a los moderadores (superusers + managers/admins del club)
2. **Moderador aprueba/rechaza usuario** → Email al usuario
3. **Usuario sube imagen** → Email a los moderadores
4. **Moderador modera imagen** → Email al usuario
5. **10+ errores 404 en 1 hora** → Alerta inmediata a los destinatarios técnicos
6. **Reporte diario 404** → Cron job (configurar por separado)

## 📋 Configuración de Reporte Diario 404

Para el reporte diario, añade a tu crontab:

```bash
# Editar crontab
crontab -e

# Añadir línea (envía reporte a las 8:00 AM todos los días)
0 8 * * * /usr/bin/docker compose -f /ruta/a/tu/proyecto/docker-compose.yml exec -T web python manage.py shell -c "from ilovevoley.core.middleware import send_404_daily_report; send_404_daily_report()"
```

O usando Django-Q/Celery si los tienes configurados.

## 🎨 Personalización de Templates

Los templates están en `ilovevoley/templates/emails/`:

- `base_email.html` - Template base con estilos
- `new_user_pending.html` - Usuario pendiente
- `new_membership_pending.html` - Membresía pendiente en un club
- `reactivation_pending.html` - Reactivación de cuenta pendiente
- `user_approved.html` / `user_rejected.html` - Usuario aprobado / rechazado
- `user_inactivity_warning.html` - Aviso de inactividad
- `image_pending.html` / `images_pending_batch.html` - Imagen(es) pendiente(s)
- `image_approved.html` - Imagen aprobada
- `image_rejected.html` - Imagen rechazada
- `404_daily_report.html` - Reporte diario 404
- `404_alert.html` - Alerta inmediata 404
- `vision_api_error.html` - Error de Google Vision
- `person_link_approved.html` / `person_link_rejected.html` - Vínculo cuenta ↔ ficha
- `season_wrapped.html` / `season_highlights.html` - Wrapped y novedades de temporada
- `league_candidates_pending.html` / `team_identity_candidates_pending.html` - Ligas e identidades por validar
- `admin_direct_message.html` - Mensaje directo del admin

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
   docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=config
   ```

2. **Revisar logs**:
   ```bash
   docker compose logs web celery-default | grep -i email
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

- Verificar que `ilovevoley/templates` está en `TEMPLATES.DIRS`
- Comprobar permisos de archivos
- Revisar sintaxis de templates Django

## 📊 Monitoreo

### Logs de Email

Los envíos normales no se registran; solo los fallos y descartes (logger `ilovevoley.core.email_utils`):
```
Email no enviado: <asunto> - No hay destinatarios o configuración de email
Error enviando email: <asunto>
```

### Estadísticas

Para ver estadísticas de emails enviados, puedes crear un modelo de log personalizado o usar herramientas como:
- SendGrid Analytics
- Mailgun Logs
- Google Analytics (para links en emails)

## 🔧 Desarrollo

### Añadir Nueva Notificación

1. **Crear tarea Celery** (con `name=` explícito) que llame a `send_notification_email` y encolarla con `enqueue_on_commit`. Para avisos en el idioma de cada destinatario, `subject` acepta un callable (ver `ilovevoley.core.i18n`):
   ```python
   @shared_task(name='notify_mi_notificacion')
   def notify_mi_notificacion_task(obj_id):
       instance = MiModelo.objects.get(pk=obj_id)
       send_notification_email(
           subject=lambda: _('Mi notificación'),
           template_name='emails/mi_template.html',
           context={'objeto': instance},
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
docker compose -f docker-compose.dev.yml run --rm web python manage.py send_test_emails --test-type=all --email=tu-email-dev@example.com
```

## 📚 Referencias

- [Django Email](https://docs.djangoproject.com/en/6.0/topics/email/)
- [Gmail App Passwords](https://support.google.com/accounts/answer/185833)
- [HTML Email Best Practices](https://www.campaignmonitor.com/dev-resources/guides/html-email-guide/)

---

**💡 Tip**: Empieza con notificaciones críticas (usuarios pendientes) y ve añadiendo gradualmente otras según necesites.