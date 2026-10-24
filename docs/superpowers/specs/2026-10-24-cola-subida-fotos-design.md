# Cola de subida de fotos tolerante a mala cobertura (#611)

## Objetivo

Permitir que la subida de fotos desde móvil en pabellones con cobertura irregular sea
tolerante a cortes de red: comprimir cada imagen en cliente antes de encolarla,
persistir la cola localmente en IndexedDB, subir foto a foto con reintentos
automáticos (Background Sync donde exista + *fallback* al recuperar conexión o volver
a la app) y mostrar el progreso y los controles de reintento en un widget flotante
global que permita seguir navegando por la aplicación.

## Diagnóstico del flujo actual

- [`image_upload`](../../ilovevoley/content/views.py) y
  [`image_bulk_upload`](../../ilovevoley/content/views.py) envían un `POST`
  monolítico de formulario HTML (`multipart/form-data`) con hasta 20 ficheros a la
  vez, sin `fetch`, sin cola y sin reintentos. Un corte a mitad pierde todo el envío.
- En [`image_bulk_upload.html`](../../ilovevoley/content/templates/content/image_bulk_upload.html),
  `createOptimizedPreview()` solo redimensiona el `<canvas>` para la miniatura en
  pantalla; al enviar el formulario se adjuntan los ficheros originales de cámara sin
  comprimir, pese a que [`Image.save()`](../../ilovevoley/content/models/content.py)
  en servidor siempre sanea a `<= 2560 px` y JPEG calidad `85` mediante
  [`sanitize_image()`](../../ilovevoley/videos/utils.py).
- Los envíos procedentes del Share Target PWA (`?share=...`) ya tienen los binarios
  en servidor ([`SharedUpload`](../../ilovevoley/content/models/content.py)), por lo
  que no transfieren archivos desde el cliente y mantienen su `POST` directo.

## Decisiones

- **Widget flotante global** en [`base.html`](../../ilovevoley/templates/base.html)
  para usuarios autenticados dentro de un tenant: al pulsar «Subir» en subida
  individual o múltiple, las fotos se comprimen, se guardan en IndexedDB y el usuario
  puede cambiar de pantalla mientras la cola sube en segundo plano.
- **Compresión previa en móvil + límite de 10 MB post-compresión**:
  - Se permite seleccionar archivos de cámara de hasta **25 MB** en bruto.
  - El cliente redimensiona a lado máximo **2560 px** (respetando orientación EXIF) y
    codifica a **JPEG calidad 0.85**.
  - El límite de **10 MB** (#121) se valida sobre el archivo resultante (o sobre el
    original si el navegador no decodifica HEIC en `<canvas>`, en cuyo caso el
    servidor lo convierte con `pillow-heif` como hasta ahora).
  - El servidor mantiene intacto [`sanitize_model_image_field()`](../../ilovevoley/videos/utils.py)
    en `Image.save()` para garantizar la eliminación de EXIF/GPS (#86).
- **Sin migración de base de datos**:
  - **Idempotencia** mediante caché Redis (TTL 24 h) indexada por
    `upload_idempotency:{tenant_id}:{user_id}:{client_upload_id}` para evitar fotos
    duplicadas cuando la petición llega al servidor pero la respuesta se corta en la
    red del pabellón.
  - **Agrupación de avisos por lote (`batch_id`)** con debounce en caché + Celery
    (`countdown`), siguiendo el patrón de [`queue_match_media_push()`](../../ilovevoley/content/services.py),
    para emitir un único email [`notify_images_pending_batch_task`](../../ilovevoley/core/tasks.py)
    y un único push `new_album` por tanda.

## Arquitectura cliente (IndexedDB + `upload_queue.js` + `sw.js`)

### 1. Almacenamiento en IndexedDB (`ilovevoley_upload_queue`, v1)

Object store `uploads` con `keyPath: 'client_upload_id'` e índices por
`tenant_origin` y `status`:

- `client_upload_id`: UUID v4 único por foto.
- `batch_id`: UUID v4 compartido por las fotos encoladas en una misma acción de
  «Subir».
- `tenant_origin`: `window.location.origin` (aísla las colas por club/subdominio).
- `csrf_token`: último token CSRF disponible al encolar o refrescado desde
  `window.getCsrfToken()`.
- `file_blob`: `Blob` JPEG comprimido (o `File` original en fallback HEIC `<= 10 MB`).
- `file_name`: nombre normalizado (`.jpg` si fue comprimido).
- `preview_data_url`: miniatura ligera (~120 px) para mostrar en la lista de la cola.
- `metadata`:
  - `title`, `description`, `image_type`, `match`, `set_number`, `season`, `tags`,
    `categories` (lista de IDs), `album_group_id`, `album_name`, `create_album`,
    `shared_title`, `seq_index`.
  - Si el usuario marcó «Agrupar todas las imágenes en un álbum» (`create_album`), el
    cliente genera un `album_group_id` (UUID v4) al crear el lote y lo incluye en
    todas las fotos del `batch_id`.
- `status`: `'pending'` | `'uploading'` | `'uploaded'` | `'error'`.
- `attempts`: número de intentos realizados (máximo automático: `4`, con backoff
  `2s, 5s, 12s, 25s`).
- `error_message`: texto de error en caso de fallo definitivo o agotamiento de
  reintentos.
- `created_at`, `updated_at`.

Al inicializar la cola se purgan registros con antigüedad `> 7 días` y los que hayan
quedado bloqueados en `'uploading'` por cierre abrupto de pestaña (> 2 min sin
actualizarse) vuelven a `'pending'`.

### 2. Coordinación de subida, reintentos y Background Sync

- **Subida secuencial (1 a 1)**: evita saturar el enlace móvil y garantiza el orden
  secuencial de títulos (`001, 002…`).
- **Clasificación de fallos**:
  - Error de red (`fetch` rechazado), timeout (45 s por foto), HTTP `408`, `429`,
    `502`, `503`, `504`: si `navigator.onLine === false`, la foto vuelve a
    `'pending'` sin consumir intentos y espera al evento `online` o `sync`; si hay
    red, reintenta con backoff exponencial hasta `4` intentos antes de pasar a
    `'error'`.
  - HTTP `400`, `403`, `422`: fallo de validación o permisos; pasa directamente a
    `'error'` mostrando el mensaje devuelto por el servidor.
- **Background Sync y *fallback* multi-navegador**:
  - Al encolar, si `'serviceWorker' in navigator` y `'SyncManager' in window`, se
    registra `registration.sync.register('sync-photo-uploads')`.
  - En [`sw.js`](../../ilovevoley/static/js/sw.js), el listener `sync` para
    `'sync-photo-uploads'` comprueba si hay algún `WindowClient` del mismo origen:
    si existe uno visible, le envía `postMessage({ type: 'PROCESS_UPLOAD_QUEUE' })`;
    si la app está en segundo plano o cerrada, el propio `sw.js` lee los ítems
    `'pending'` de IndexedDB para `self.location.origin`, los envía a
    `/content/api/imagenes/subir/` y notifica cambios de estado por `postMessage` a
    las ventanas abiertas.
  - En **Safari / iOS** (y navegadores sin `SyncManager`), `upload_queue.js` reanuda
    automáticamente la cola en `DOMContentLoaded`, `window.addEventListener('online')`
    y `document.addEventListener('visibilitychange')` (cuando pasa a `visible`).

### 3. Widget flotante de progreso y acciones manuales

- Incluido en [`base.html`](../../ilovevoley/templates/base.html) e inicializado por
  `static/js/upload_queue.js` (precached también en `sw.js`).
- Cumple la CSP estricta del proyecto: sin `onclick` ni `style=` inline; todas las
  acciones usan atributos `data-call` gestionados por
  [`csp_actions.js`](../../ilovevoley/static/js/csp_actions.js) y el ancho de la barra
  de progreso usa `<progress>` nativo estilizado con Tailwind/CSS.
- Estados visuales por ítem: `Pendiente`, `Subiendo`, `Subida`, `Error` (con motivo).
- Controles:
  - **Reintentar** (por foto o «Reintentar fallidas», que reinicia `attempts = 0` y
    pone `status = 'pending'`).
  - **Eliminar / descartar** una foto pendiente o con error de la cola local.
  - **Minimizar / desplegar** detalle de la cola y **Cerrar** cuando todas las fotos
    están en `uploaded`.

## Backend (`/content/api/imagenes/subir/` y consolidación de lote)

### 1. Endpoint `image_queue_upload_api`

Ruta `POST /content/api/imagenes/subir/` (`content:image_queue_upload_api`), protegida
con `@tenant_access_required()` y `@require_POST`:

1. Valida `client_upload_id` (UUID) y comprueba en caché la clave
   `upload_idempotency:{tenant.id}:{request.user.id}:{client_upload_id}`. Si ya existe
   y la `Image` asociada sigue en base de datos, devuelve `200 OK` con
   `{'ok': True, 'image_id': image.id, 'status': image.status, 'deduplicated': True}`.
2. Valida archivo (`image`, máx. 10 MB, extensiones permitidas) y metadatos:
   - Si viene `album_group_id` (UUID válido):
     - Si el álbum ya tiene fotos en otro tenant distinto de `request.tenant`, rechaza
       con `400`.
     - Si es un álbum nuevo del lote (`create_album=true` y `album_name` no vacío) o
       un álbum existente del mismo tenant, asigna `album_group_id` y `album_name`.
   - Calcula el título descriptivo secuencial igual que `image_upload` /
     `image_bulk_upload` (`build_descriptive_title` + `get_next_sequence_number`).
   - Guarda la instancia `Image` (que ejecuta `sanitize_model_image_field`, asigna
     temporada/categorías y programa miniaturas con `schedule_thumbnail_generation`).
   - Encola `analyze_image_with_vision_task(image.id, notify_if_pending=False)` si
     `GOOGLE_VISION_ENABLED` está activo y el usuario no es superusuario.
3. Guarda `image.id` en la clave de idempotencia en caché con TTL de 24 horas (`86400` s).
4. Registra la foto en el agregador por lote (`queue_upload_batch_notifications`) y,
   si la foto quedó aprobada y tiene `match_id`, llama a `queue_match_media_push`.
5. Devuelve `JsonResponse({'ok': True, 'image_id': image.id, 'title': image.title, 'status': image.status})`.

### 2. Debounce de notificaciones por lote (`batch_id`)

Función `queue_upload_batch_notifications(organization_id, batch_id, image_id, *, is_pending, is_new_album, album_group_id, album_name, category_ids)` en `ilovevoley/content/services.py` + tarea Celery `flush_upload_batch_notifications_task` (`name='content.flush_upload_batch_notifications'`) en `ilovevoley/content/tasks.py`:

- Acumula en caché (`upload_batch_state:{organization_id}:{batch_id}`, TTL 1 h) los
  `pending_ids` y los datos del nuevo álbum si `is_new_album=True`.
- Programa con `cache.add` una ejecución diferida (`countdown = settings.UPLOAD_BATCH_DEBOUNCE_SECONDS`, por defecto `15` s) de `flush_upload_batch_notifications_task(organization_id, str(batch_id))`.
- Cuando la tarea se ejecuta tras la ventana de silencio:
  - Si hay `pending_ids` y `EMAIL_NOTIFICATIONS['image_pending']` está activo,
    invoca `notify_images_pending_batch_task` (si aún quedan fotos pendientes tras
    Vision API).
  - Si `is_new_album` es verdadero y aún no se envió el push de ese `album_group_id`
    (controlado por clave `upload_album_push_sent:{organization_id}:{album_group_id}`),
    despacha `notify_web_push_organization_task` con `notification_type='new_album'`.

## Traducciones (i18n)

- Todas las cadenas visibles en plantillas y respuestas JSON del endpoint van envueltas
  con `gettext` / `{% trans %}` (y `|escapejs` cuando se inyectan en configuración JS),
  actualizando `locale/ca/LC_MESSAGES/django.po`.

## Tests

Siguiendo `docs/ai-guidelines/testing-guidelines.md`, solo se añaden tests que
protegen decisiones de producto y caminos críticos de error:

1. **Idempotencia por `client_upload_id`**: enviar dos veces el mismo
   `client_upload_id` para el mismo usuario y tenant crea una sola fila `Image`,
   devuelve `deduplicated=True` en el segundo intento y no duplica tareas de Vision ni
   notificaciones.
2. **Aislamiento multi-tenant y álbumes por lote**: enviar varias fotos con el mismo
   `album_group_id` y `album_name` desde la cola las agrupa en el mismo álbum, pero
   intentar usar un `album_group_id` perteneciente a otro tenant devuelve `400`.
3. **Consolidación de avisos por `batch_id`**: múltiples subidas unitarias con el mismo
   `batch_id` producen un único email de moderación en lote y un único push de nuevo
   álbum al ejecutarse `flush_upload_batch_notifications_task`.
4. **Saneamiento y límites**: el endpoint rechaza archivos `> 10 MB` o de formato no
   válido con `400` JSON y purga metadatos EXIF/GPS al guardar.

## Fuera de alcance

- Subidas troceadas (chunked/TUS) de vídeo o de un mismo archivo en fragmentos.
- Modificar el almacenamiento efímero de `SharedUpload` (#524, #599), que ya reside en
  el servidor.
