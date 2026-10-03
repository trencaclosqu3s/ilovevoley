# 🔔 Sistema de Notificaciones Web Push (VAPID)

Documentación técnica, configuración y operación del sistema de notificaciones Web Push en I Love Voley.

---

## 🎯 Visión General

El sistema de notificaciones Web Push permite enviar avisos instantáneos y segmentados a los navegadores y dispositivos móviles de los aficionados y miembros del club, cumpliendo el estándar abierto **VAPID (RFC 8292)**.

### Características Principales
- **Cero dependencias de SDKs propietarios**: Comunicación directa con los servidores push estándar (Google FCM, Apple Web Push, Mozilla Push Service, Microsoft WNS).
- **Segmentación por Categorías**: Los usuarios pueden elegir en su perfil qué categorías deportivas seguir (Senior, Juvenil, Cadete, etc.), recibiendo avisos únicamente de sus equipos.
- **Traducción Automática**: Mensajes localizados en el idioma de cada usuario (`es` o `ca`) mediante el helper `push_message(builder)` de `ilovevoley.core.i18n`.
- **Ventana de Agrupación (Debounce)**: La subida de múltiples fotografías a un partido genera un solo aviso agrupado en lugar de saturar al usuario con notificaciones repetitivas.
- **Auditoría de Envíos y Auto-Limpieza**: Registro de estadísticas de entrega (`WebPushAudit`) y purga periódica de suscripciones caducadas y registros antiguos.

---

## ⚙️ Configuración y Variables de Entorno

### 1. Variables de Entorno (`.env`)

```bash
# Claves criptográficas VAPID (RFC 8292)
VAPID_PUBLIC_KEY="BC..."
VAPID_PRIVATE_KEY="MC..."
VAPID_CLAIMS_SUB="mailto:admin@ilovevoley.es"

# Cooldown y agrupación de subidas multimedia de partidos (en segundos, por defecto 300 = 5 min)
MATCH_MEDIA_PUSH_DEBOUNCE_SECONDS=300
```

### 2. Generación de Claves VAPID

Para generar un nuevo par de claves en desarrollo o producción:

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py generate_vapid_keys
```

El comando generará la clave pública (P-256 codificada en Base64 URL-safe) y la clave privada correspondientes.

---

## 🏛️ Modelo de Datos (`ilovevoley.users.models`)

### 1. `WebPushSubscription`
Almacena el registro de cada dispositivo suscrito:
- `endpoint`: URL única provista por el navegador/gateway push (clave única).
- `p256dh`: Clave pública de curva elíptica del cliente para cifrado de carga útil.
- `auth`: Secreto de autenticación compartido.
- `user`: Clave foránea opcional a `User` (soporta dispositivos anónimos y autenticados).
- `organization`: Organización/club desde la que se originó la suscripción.
- `user_agent`: Identificador del navegador para telemetría básica.

### 2. `CategoryPreference`
Relaciona a un usuario con sus categorías deportivas de interés (`categories` M2M con `core.Category`) por organización. Quien no especifique ninguna preferencia recibe los avisos de todas las categorías.

### 3. `NotificationPreference`
Permite a los usuarios activar o desactivar selectivamente tipos concretos de aviso para un club (`match_result`, `album_published`, etc.).

### 4. `WebPushAudit`
Registra el resultado de cada difusión masiva de notificaciones:
- `organization`: Club emisor del aviso.
- `notification_type`: Tipo de notificación enviada.
- `match_id`: ID del partido relacionado (si aplica).
- `candidates_count`: Dispositivos candidatos antes de filtros.
- `dispatched_count`: Notificaciones entregadas con éxito al gateway push.
- `failed_count`: Notificaciones fallidas.
- `created_at`: Timestamp de auditoría.

---

## 🛡️ Seguridad y Mitigación SSRF

Dado que los navegadores envían URLs de endpoint arbitrarias al suscribirse, el backend valida estrictamente el destino antes de cualquier petición HTTP para evitar vulnerabilidades de tipo **Server-Side Request Forgery (SSRF)**:

- **Función de Validación** (`ilovevoley.users.webpush.is_valid_push_endpoint`):
  1. Requiere esquema `https://`.
  2. Longitud máxima acotada a 500 caracteres.
  3. Comprueba que el hostname pertenezca a la lista blanca de proveedores oficiales:
     - `fcm.googleapis.com`
     - `updates.push.services.mozilla.com`
     - `web.push.apple.com` y subdominios `*.push.apple.com`
     - `*.notify.windows.com`
- **Timeout Estricto**: Cada envío tiene un timeout máximo de 10 segundos (`PUSH_REQUEST_TIMEOUT_SECONDS`) para evitar que gateways no responsivos retengan los workers de Celery.

---

## 🚀 Despacho Asíncrono de Avisos (Celery)

### Tarea de Envío: `notify_web_push_organization`
Nombre registrado: `notify_web_push_organization` (`ilovevoley.users.tasks`).

```python
notify_web_push_organization_task.delay(
    organization_id=org.id,
    title='Victoria del Senior!',
    body='Sant Josep 3 - 1 CV Manacor',
    url='/competitions/partidos/123/',
    badge_count=1,
    category_ids=[category.id],
    notification_type='match_result',
    translations={
        'ca': {'title': 'Victòria del Sènior!', 'body': 'Sant Josep 3 - 1 CV Manacor'},
    },
    match_id=123,
)
```

#### Reglas de Despacho:
1. **Multi-Club**: Un dispositivo suscrito en el club A recibe notificaciones del club B si el usuario es miembro aprobado del club B.
2. **Filtrado por Categoría**: Si se especifica `category_ids`, solo se notifica a usuarios con interés en esas categorías (o sin preferencias fijadas).
3. **Localización de Texto**: Se selecciona el texto en el idioma preferido de cada destinatario (`language_for(user)`).
4. **URL de Destino Contextual**: Si la URL es relativa, se expande al subdominio del club emisor (`build_absolute_url(url, tenant=org)`), de forma que al hacer clic se abre el club correspondiente.
5. **Auto-Depuración (404/410)**: Si el servicio push responde HTTP 404 o 410 (Gone/Revoked), la suscripción caducada se elimina automáticamente de la base de datos.
6. **Auditoría**: Se guarda una fila en `WebPushAudit` con el desglose de resultados.

---

## 📸 Casos de Uso y Disparadores

### 1. Publicación de Fotos y Álbumes con Debounce
- **Disparador**: Subida y aprobación de imágenes de un partido (`ilovevoley.content.views`).
- **Comportamiento**: En lugar de enviar un push por cada foto individual subida, se programa la tarea Celery `notify_match_media_push` con una cuenta atrás (`countdown=MATCH_MEDIA_PUSH_DEBOUNCE_SECONDS`).
- Si se siguen subiendo fotos del mismo partido dentro de la ventana de espera, se renueva la ventana, garantizando un **único aviso consolidado**: *"Se han añadido 15 fotos del partido..."*.

### 2. Actualización de Marcadores de Partidos
- **Disparador**: Modificación o cierre del marcador oficial de un partido (`ilovevoley.competitions.views` o scraping federativo).
- Envía inmediatamente un push a los usuarios interesados en esa liga/categoría.

---

## 🧹 Tareas Periódicas de Mantenimiento

Configuradas mediante Celery Beat:

| Nombre de Tarea | Frecuencia Sugerida | Descripción |
| :--- | :--- | :--- |
| `cleanup_expired_web_push_audits` | Semanal (`0 3 * * 0`) | Purga los registros de auditoría `WebPushAudit` con más de 90 días de antigüedad. |

---

## 🧪 Verificación y Tests

Para ejecutar la suite de pruebas del módulo de Web Push:

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest \
  ilovevoley/users/tests/test_webpush_models.py \
  ilovevoley/users/tests/test_webpush_tasks.py \
  ilovevoley/users/tests/test_webpush_views.py \
  ilovevoley/users/tests/test_vapid_config.py \
  ilovevoley/competitions/tests/test_match_push_trigger.py \
  ilovevoley/content/tests/test_album_push_trigger.py --create-db
```
