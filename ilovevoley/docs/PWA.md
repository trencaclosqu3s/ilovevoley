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

### Aviso único para activar notificaciones
`webpush.js` (cargado en todas las páginas) muestra el banner `#webpush-prompt` (en `navbar.html`) una sola vez: solo en la PWA instalada (`display-mode: standalone`), con sesión iniciada, con push soportado, permiso no denegado y sin suscripción. Descartar, o aceptar con la suscripción completada, guarda `ilovevoley.webpush.prompt_seen` en `localStorage` (también se guarda si ya había suscripción) y aceptar lleva a la selección de categorías (`profile_edit#push-notifications`); si suscribir falla, el banner se oculta sin marcarse como visto ni navegar. Si `localStorage` no está disponible, el aviso reaparecerá en cada apertura.

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
