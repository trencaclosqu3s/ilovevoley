# 📧 Cambio a Sistema Dinámico de Emails para Administradores

## 🎯 Resumen del Cambio

Se ha mejorado el sistema de notificaciones por email para que **automáticamente** envíe notificaciones a todos los usuarios superuser con email configurado en la base de datos, eliminando la necesidad de mantener una lista manual de emails en el archivo `.env`.

## ✅ Beneficios

1. **Gestión Dinámica**: Los emails se obtienen directamente de la base de datos
2. **Cero Mantenimiento**: No necesitas actualizar el `.env` al añadir/quitar admins
3. **Centralizado**: Todo se gestiona desde el panel de Django Admin
4. **Menos Errores**: No hay riesgo de emails desactualizados en configuración
5. **Más Seguro**: Los emails de admin no están hardcodeados en archivos de configuración

## 🔧 Cambios Técnicos Realizados

### Archivos Creados:
- **`videosvoley/core/email_utils.py`**: Utilidades centralizadas para email
  - `get_admin_emails()`: Obtiene dinámicamente emails de superusers
  - `send_notification_email()`: Función unificada para envío de notificaciones

### Archivos Modificados:
- **`videosvoley/users/signals.py`**: Ahora usa `email_utils` centralizado
- **`videosvoley/videos/signals.py`**: Ahora usa `email_utils` centralizado  
- **`videosvoley/core/middleware.py`**: Usa `get_admin_emails()` para reportes 404
- **`videosvoley/users/management/commands/test_email_notifications.py`**: Actualizado para usar el sistema dinámico
- **`videosvoley/docs/NOTIFICACIONES_EMAIL.md`**: Documentación actualizada

### Eliminado:
- ❌ Dependencia obligatoria de `ADMIN_EMAIL_LIST` en `.env`
- ❌ Código duplicado de `send_notification_email()` en múltiples archivos

## 📋 Migración

### Antes:
```bash
# .env
ADMIN_EMAIL_LIST=admin1@example.com,admin2@example.com,admin3@example.com
```

Cada vez que añadías/quitabas un admin, tenías que:
1. Editar el archivo `.env`
2. Reiniciar los contenedores Docker

### Ahora:
```bash
# .env
NOTIFICATION_EMAIL_ENABLED=True
# ADMIN_EMAIL_LIST ya no es necesario (pero se mantiene como fallback opcional)
```

Los emails se obtienen automáticamente de los usuarios que cumplan:
- `is_superuser=True`
- `email` configurado y no vacío

## 🚀 Cómo Usar

### Para que un usuario reciba notificaciones:

1. **Desde Django Admin**:
   - Ir a Usuarios → Seleccionar usuario
   - Marcar ✅ "Superuser status"
   - Configurar el campo "Email"
   - Guardar

2. **Desde shell**:
   ```bash
   docker-compose exec web python manage.py shell
   ```
   ```python
   from django.contrib.auth import get_user_model
   User = get_user_model()
   
   # Crear superuser con email
   user = User.objects.get(username='miusuario')
   user.is_superuser = True
   user.email = 'admin@example.com'
   user.save()
   ```

### Verificar superusers que recibirán emails:

```bash
docker-compose exec web python manage.py shell
```
```python
from videosvoley.core.email_utils import get_admin_emails
print(get_admin_emails())
# ['admin1@example.com', 'admin2@example.com']
```

## 🧪 Probar el Sistema

```bash
# Verificar configuración y ver qué superusers tienen email
docker-compose exec web python manage.py test_email_notifications --test-type=config

# Enviar emails de prueba a todos los superusers
docker-compose exec web python manage.py test_email_notifications --test-type=all

# Enviar a un email específico para pruebas
docker-compose exec web python manage.py test_email_notifications --test-type=all --email=tu-email@gmail.com
```

## ⚠️ Compatibilidad con Configuración Anterior

El sistema mantiene **compatibilidad hacia atrás**:
- Si no hay superusers con email, usará `ADMIN_EMAIL_LIST` como fallback
- Si tienes `ADMIN_EMAIL_LIST` configurado, seguirá funcionando pero será ignorado si hay superusers con email

**Recomendación**: Elimina `ADMIN_EMAIL_LIST` de tu `.env` para aprovechar el sistema dinámico.

## 📊 Tipos de Notificaciones Afectadas

Todas las notificaciones a administradores ahora usan el sistema dinámico:

✅ Nuevo usuario pendiente de aprobación
✅ Nueva imagen pendiente de moderación
✅ Reporte diario de errores 404
✅ Alerta inmediata de múltiples errores 404

**Nota**: Las notificaciones a usuarios individuales (usuario aprobado, imagen moderada) NO se ven afectadas, siguen enviándose al email del usuario específico.

## 🐛 Solución de Problemas

### "No se envían emails a los admins"

1. Verificar que hay superusers con email:
   ```bash
   docker-compose exec web python manage.py shell
   ```
   ```python
   from django.contrib.auth import get_user_model
   User = get_user_model()
   User.objects.filter(is_superuser=True).values('username', 'email', 'is_superuser')
   ```

2. Verificar que `NOTIFICATION_EMAIL_ENABLED=True` en `.env`

3. Verificar configuración SMTP:
   ```bash
   docker-compose exec web python manage.py test_email_notifications --test-type=config
   ```

### "Quiero añadir un email adicional que no es superuser"

Puedes usar `ADMIN_EMAIL_LIST` como complemento:
```bash
ADMIN_EMAIL_LIST=email-adicional@example.com
```
Este email se añadirá a la lista si no hay superusers disponibles.

## 📝 Próximos Pasos (Opcional)

- Considerar añadir grupos de permisos para notificaciones específicas
- Implementar preferencias de notificación por usuario
- Dashboard de gestión de notificaciones en el admin

---

**Fecha del cambio**: Octubre 2025  
**Implementado por**: Sistema de mejora continua I Love Voley
