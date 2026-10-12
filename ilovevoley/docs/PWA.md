# Progressive Web App (PWA)

Documentación técnica y operativa de la PWA instalable de I Love Voley.

---

## 📱 Concepto y Arquitectura

I Love Voley implementa el modelo de **App Única Comunitaria**: en lugar de publicar aplicaciones independientes por club, el sistema ofrece una única aplicación web progresiva instalable en dispositivos móviles (Android / iOS) y escritorio (Chrome, Edge, Safari).

### Características Fundamentales
1. **Instalación Directa**: Instalable como aplicación independiente (`display: standalone`) desde el navegador con un solo clic.
2. **Identidad Dinámica de Tenant**: Aunque la PWA tiene el nombre universal "I Love Voley", el tema visual (`theme_color`), la cabecera y el entorno gráfico se adaptan dinámicamente al club activo en cada momento.
3. **Navegación Multi-Club In-App**: Gracias al soporte de **Scope Extensions**, un usuario puede alternar entre clubes federados (`santjosep.ilovevoley.es`, `cvsoller.ilovevoley.es`, etc.) sin salirse de la ventana de la aplicación.
4. **Resiliencia Offline**: Caché inteligente de recursos estáticos críticos y pantalla de contingencia con diseño propio cuando no hay conexión.
5. **Avisos Web Push y App Badging**: Recepción nativa de notificaciones push y contador en el icono de la app en sistemas compatibles.
6. **Retroceso In-App**: En `display: standalone` el navegador no muestra sus flechas de navegación (y en iOS no existe gesto de swipe). La cabecera incorpora un botón "atrás" propio para no perder el contexto ni los filtros al volver.

---

## 🛠️ Componentes Técnicos

### 1. Web App Manifest Dinámico (`/manifest.webmanifest`)
Implementado en `ilovevoley.core.views.manifest_json`:
- **Nombre e Identidad**: `name: 'I Love Voley'`, `short_name: 'ILoveVoley'`, `id: '/'`.
- **`theme_color` Dinámico**: Si la petición proviene del subdominio de un club, toma `Organization.primary_color`; en el dominio raíz usa el color de marca por defecto.
- **Iconos**:
  - `icon-192.png`: 192×192 px (`purpose: any`)
  - `icon-512.png`: 512×512 px (`purpose: any`)
  - `icon-maskable-512.png`: 512×512 px (`purpose: maskable` para recorte redondeado o squircle en Android)
- **Cabeceras HTTP**: `Content-Type: application/manifest+json; charset=utf-8`, `Vary: Host`, `Cache-Control: public, max-age=3600`.

### 2. Service Worker (`/sw.js`)
Servido por la vista `ilovevoley.core.views.service_worker` desde la raíz con la cabecera `Service-Worker-Allowed: /` y `Cache-Control: no-cache, no-store, must-revalidate`.

#### Ciclo de Vida y Estrategia de Caché:
- **`install` (Precache Resiliente)**:
  - Precachea `/offline/`, CSS principal (`app.css`), acciones CSP (`csp_actions.js`), logo e iconos.
  - Cada recurso se procesa individualmente (`Promise.all` con `.catch(() => undefined)`): si un recurso no está disponible temporalmente, la instalación del Service Worker no se cancela.
- **`activate` (Purga de Versiones)**:
  - Elimina automáticamente cachés obsoletas con prefijo `ilovevoley-pwa-` que difieran de `CACHE_NAME`.
- **`fetch`**:
  - **Exclusiones de Red**: Rutas mutables o privadas (`/media/`, `/admin/`, `/accounts/`, `/api/`, `sw.js`, `manifest.webmanifest`) se delegan siempre a la red sin pasar por caché.
  - **Navegación (`mode === 'navigate'`)**: Estrategia **Network-First** con fallback a `/offline/` solo si la conexión de red falla completamente.
  - **Recursos Estáticos (`/static/`)**: Estrategia **Stale-While-Revalidate** para peticiones GET que respondan 200 OK en el mismo origen.

### 2b. Share Target (`share_target` del manifiesto)

- El manifiesto declara `share_target` (POST multipart a `/content/imagenes/compartida/`)
  con `params.files[].name = "image"` y `multiple: true`: la app aparece en la hoja de
  **Compartir** de Android (Chrome/Edge/Samsung Internet) con la PWA instalada.
- La vista receptora (`content.views.image_share_target`) exige sesión + membresía
  aprobada en el tenant del subdominio; valida tipo/tamaño por archivo (JPG/PNG/WebP/
  HEIC/HEIF, ≤10 MB, máx 20 por lote) y guarda los válidos en `SharedUpload` (TTL 24 h,
  purga oportunista al recibir). Redirige al flujo normal: 1 archivo →
  `imagenes/subir/?share=<token>`, N → `imagenes/subir-multiples/?share=<batch>`.
- El consumo reconstruye `FILES` desde la fila temporal y recorre la subida existente
  sin cambios (Vision, miniaturas, nomenclatura, categorías, push). CSRF: solo el
  receptor va exento (el navegador no puede enviar token en un share target); el
  consumo mantiene CSRF normal.
- **Contrato con el SW**: `sw.js` no intercepta `image_share_target` porque su guard
  de no-GET devuelve la petición a red directa. Cualquier caché futura de
  navegaciones NO debe envolver `POST /content/imagenes/compartida/`.
- **iOS**: Safari no implementa `share_target`; la app no aparece en su hoja de
  compartir. Usar la subida web normal dentro de la app instalada.
- **Despliegue**: verificar `client_max_body_size` en Nginx (varias fotos desde el
  móvil pueden superar el default de 1 MB → el POST del share target fallaría sin
  explicación). Acción de servidor, no de código.

### 3. Pantalla de Fallback Offline (`/offline/`)
- Servida por `ilovevoley.core.views.offline_view` utilizando la plantilla `ilovevoley/templates/offline.html`.
- Informa al usuario de la pérdida de conectividad, proporciona un botón interactivo de reintento (`data-action="reload"`) y mantiene la coherencia visual de la plataforma.

### 4. Navegación In-App (`static/js/pwa_nav.js`)
- El botón `#pwa-back-button` de la navbar solo se muestra cuando la app corre instalada (`display-mode: standalone` o `navigator.standalone` en iOS) y no estamos en la portada del club.
- Retrocede con `history.back()`; si no hay historial interno (acceso directo desde un push, por ejemplo) navega a la portada del club. Al usar el historial del navegador, los filtros de la página previa (p. ej. Resultados) se conservan.
- Complementariamente, `static/js/results.js` guarda los filtros de Resultados en `sessionStorage` y los reaplica si se entra a la página sin parámetros (por ejemplo desde el menú).

---

## 🌐 Convivencia Multi-Tenant y Scope Extensions

En un entorno multi-tenant basado en subdominios federados, los navegadores consideran cada subdominio un origen web distinto. Por defecto, hacer clic en un enlace a otro subdominio expulsaría al usuario de la PWA a una pestaña externa del navegador.

Para evitar esta fragmentación:

1. **Cookie de Sesión Unificada**:
   En producción, `SESSION_COOKIE_DOMAIN = '.ilovevoley.es'` y `CSRF_COOKIE_DOMAIN = '.ilovevoley.es'` permiten mantener la sesión activa entre subdominios.
2. **`scope_extensions` en el Manifiesto**:
   El manifiesto expone los orígenes permitidos:
   ```json
   "scope_extensions": [
     {"origin": "https://ilovevoley.es"},
     {"origin": "https://*.ilovevoley.es"}
   ]
   ```
3. **Origin Association (`/.well-known/web-app-origin-association`)**:
   Implementado en `ilovevoley.core.views.web_app_origin_association`:
   - Publica el mapeo de todos los subdominios de organizaciones activas.
   - La respuesta se cachea (`PWA_ORIGIN_ASSOCIATION_CACHE_KEY`) durante 24 horas y se invalida automáticamente mediante señales (`post_save`/`post_delete`) cuando se crea, edita o desactiva una organización.

---

## 🔔 App Badging y Eventos Push

El Service Worker (`sw.js`) gestiona los eventos del estándar W3C Push y App Badging:
- **Evento `push`**:
  - Deserializa el payload JSON recibido del servidor VAPID.
  - Invoca `self.registration.showNotification(title, options)`.
  - Si el payload incluye `badge_count` y la API `navigator.setAppBadge` está disponible, actualiza el contador numérico del icono de la PWA.
- **Evento `notificationclick`**:
  - Cierra la notificación activa.
  - Limpia el contador con `navigator.clearAppBadge()`.
  - Busca si ya existe una ventana abierta de la aplicación (`clients.matchAll`):
    - Si existe y coincide en origen, le devuelve el foco y navega internamente a la URL de destino (`target_url`).
    - Si no existe o pertenece a otro club, abre una nueva ventana mediante `clients.openWindow(fullTargetUrl)`.

### Aviso para activar notificaciones (snooze / rechazo)
`webpush.js` (cargado en todas las páginas) muestra el banner `#webpush-prompt` (en `navbar.html`) en la PWA instalada (`display-mode: standalone`), con sesión, push soportado, permiso no denegado y sin suscripción en ese dispositivo. Tres salidas: **Activar** (suscribe y lleva a `/profile/?tab=avisos#activar`), **Ahora no** (snooze 7 días en `ilovevoley.webpush.prompt_snooze_until`) y **No, gracias** (no volver a preguntar: `ilovevoley.webpush.prompt_never`). La clave antigua `prompt_seen` ya no se usa, así quien descartó el aviso único (#412) puede volver a verlo. Si el usuario tiene categorías de interés, el copy insiste en que las preferencias están guardadas pero el móvil aún no recibe avisos. Si `localStorage` no está disponible, el aviso puede reaparecer en cada apertura.

---

## 🧪 Verificación y Pruebas

Para validar el funcionamiento de todos los componentes PWA:

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest \
  ilovevoley/core/tests/test_pwa_manifest.py \
  ilovevoley/core/tests/test_pwa_sw.py \
  ilovevoley/core/tests/test_pwa_offline.py \
  ilovevoley/core/tests/test_pwa_icons.py \
  ilovevoley/core/tests/test_pwa_templates.py \
  ilovevoley/core/tests/test_pwa_landing_memberships.py --create-db
```
