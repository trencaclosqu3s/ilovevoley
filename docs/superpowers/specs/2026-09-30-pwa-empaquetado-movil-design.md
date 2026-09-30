# Empaquetado Móvil Ligero: App Única Comunitaria PWA y Decisión Técnica

**Fecha:** 2026-09-30  
**Estado:** Aprobado para especificación  
**Issue:** [#227](https://github.com/trencaclosqu3s/ilovevoley/issues/227) (Hija de [#226](https://github.com/trencaclosqu3s/ilovevoley/issues/226))  
**Apps afectadas:** `ilovevoley.core`, templates base y configuración de URLs (`config/urls.py`)

---

## 1. Contexto, Visión y Decisión de Producto

### Visión de Marca Unificada: App Comunitaria "I Love Voley"
I Love Voley no es una solución de marca blanca fragmentada por club, sino una **plataforma comunitaria de voleibol** que reúne a clubes, jugadores, entrenadores y familias.

Por decisión de producto:
1. **Una sola aplicación en el móvil**: La app instalada en la pantalla de inicio (y la futura app en tiendas) se llama **I Love Voley**, luce el icono oficial de la plataforma y centraliza el acceso.
2. **Acceso inteligente y conmutación de club**:
   - Si el usuario pertenece a **un único club**, al abrir la app entra directamente al contenido y partidos de su club sin pasos intermedios.
   - Si pertenece a **varios clubes** (o es árbitro/seguidor de varios equipos), la app le muestra sus clubes destacados en la cabecera ("Tus clubes") para entrar con un toque, y puede cambiar de club en cualquier momento desde la barra de navegación.
   - Si no está autenticado, la app funciona como el catálogo y punto de encuentro del voleibol federado.
3. **PWA primero, tiendas después**: La versión 1 se implementa como PWA instalable de fricción cero. El empaquetado para tiendas (Capacitor / TWA) queda documentado como decisión de arquitectura (ADR) para cuando se requieran notificaciones push nativas o presencia en Google Play / App Store.

---

## 2. Especificación Técnica

### 2.1. Manifiesto Web Único y Estandarizado (`/manifest.webmanifest`)
- **Ruta centralizada**: `/manifest.webmanifest` servido mediante la vista Django `manifest_json(request)` en `ilovevoley/core/views.py`.
- **Estructura del manifiesto**:
  ```json
  {
    "id": "/",
    "name": "I Love Voley",
    "short_name": "ILoveVoley",
    "description": "Plataforma comunitaria de gestión, vídeos y seguimiento de voleibol",
    "lang": "es",
    "dir": "ltr",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "theme_color": "#9B7FBF",
    "background_color": "#ffffff",
    "icons": [
      {
        "src": "/static/images/icons/icon-192.png",
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "any"
      },
      {
        "src": "/static/images/icons/icon-512.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "any"
      },
      {
        "src": "/static/images/icons/icon-maskable-512.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "maskable"
      }
    ]
  }
  ```
- **Detalles técnicos clave**:
  - `"id": "/"`: Identificador W3C estable same-origin para que el navegador reconozca la aplicación unívocamente.
  - `background_color: "#ffffff"`: Fondo neutro y predecible para splash screen en todos los dispositivos.
  - `theme_color`: Si la petición se realiza bajo un subdominio de club (`request.tenant`), adopta el `primary_color` del club para teñir la barra de estado del navegador en consonancia con la web; en la raíz usa `#9B7FBF`.
  - **Cabeceras HTTP**:
    - `Content-Type: application/manifest+json; charset=utf-8`
    - `Cache-Control: public, max-age=3600`
    - `Vary: Host`
    - `X-Content-Type-Options: nosniff`

### 2.2. Iconos de la Aplicación
Generados desde el archivo maestro de alta resolución `ilovevoley/static/images/logo_app.png` (1024×1024) y alojados en `ilovevoley/static/images/icons/`:
- `icon-192.png` (192×192 px, propósito general)
- `icon-512.png` (512×512 px, propósito general y splash screens Android)
- `icon-maskable-512.png` (512×512 px, adaptativo Android con zona segura protegida)
- `apple-touch-icon-180.png` (180×180 px, específico para iOS Safari "Añadir a pantalla de inicio")

### 2.3. Service Worker Mínimo y Seguro (`/sw.js`)
- Servido en la raíz `/sw.js` mediante la vista Django `service_worker(request)` con:
  - `Content-Type: application/javascript; charset=utf-8`
  - `Service-Worker-Allowed: /`
  - `Cache-Control: no-cache, no-store, must-revalidate`
- **Nombre de caché**: `ilovevoley-pwa-v1`
- **Precache mínimo esencial (garantía de instalación transaccional)**:
  - `/offline/`
  - `/static/css/app.css`
  - `/static/images/icons/icon-192.png`
  - `/static/images/icons/icon-512.png`
  *(Solo assets estáticos existentes y verificados; si un asset fallara, el SW abortaría la instalación).*
- **Estrategia de peticiones (`fetch`)**:
  - `request.method !== 'GET'`: Passthrough a red sin caché.
  - Peticiones con origen distinto: Passthrough a red.
  - **Navegación (`request.mode === 'navigate'`)**:
    - Intenta red (`fetch(request)`).
    - **Solo si la promesa falla por corte de red (`catch`)**: Devuelve `/offline/` precacheado.
    - **Nunca** activar el fallback offline ante respuestas HTTP válidas de error (401, 403, 404, 429, 500).
    - **Cero almacenamiento en caché de HTML**: Protege sesiones, tokens CSRF y datos multi-tenant.
  - **Medios privados (`/media/` y `/protected-media/`)**:
    - Network-only siempre. Preserva la autenticación y el control de acceso `X-Accel-Redirect`.
  - **Assets estáticos (`/static/`)**:
    - Stale-While-Revalidate o Cache-First únicamente para respuestas HTTP 200 OK del mismo origen.
  - **Rutas dinámicas / autenticación (`/accounts/`, `/admin/`, API)**:
    - Network-only siempre.
- **Ciclo de vida**:
  - Sin `skipWaiting()` agresivo en v1 para evitar inconsistencias de scripts en pestañas abiertas; la nueva versión toma el control al cerrar y reabrir la app.
  - El evento `activate` purga cualquier caché que no coincida con el prefijo de versión actual (`ilovevoley-pwa-`).

### 2.4. Pantalla de Fallback Offline (`/offline/`)
- Vista Django pública `offline_view(request)` y plantilla `offline.html` con Tailwind CSS.
- Si se visita desde un subdominio, muestra el acento de color del tenant (`tenant_color`).
- Mensaje conciso: *"Estás sin conexión a internet"*, icono amigable y botón de reintento (`window.location.reload()`).

### 2.5. Flujo de Acceso, Membresías y Redirección en la Raíz
- En `landing` (`ilovevoley/core/views.py`):
  - **Usuario con 1 sola membresía aprobada**: Redirección `302` automática al subdominio del club (`https://{slug}.ilovevoley.es/`).
  - **Usuario con >1 membresías aprobadas**: Permanece en la landing comunitaria mostrando arriba una sección destacada **"Tus clubes"** para entrar con un toque a cualquiera de ellos.
  - **Usuario sin membresías / anónimo**: Muestra el catálogo de clubes de la comunidad para navegar o solicitar acceso.
- **Conmutación desde el club**:
  - En la barra de navegación del club, si el usuario tiene múltiples membresías (`can_switch_club = len(approved_memberships) > 1`), el botón "Cambiar de club" (`switch_club_url`) lo devuelve a la raíz comunitaria.

### 2.6. Metas y Registro en Plantillas Base
En `<head>` de `base.html` y `base_auth.html`:
```html
<link rel="manifest" href="{% url 'manifest_json' %}">
<meta name="theme-color" content="{{ tenant_color|default:'#9B7FBF' }}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="I Love Voley">
<link rel="apple-touch-icon" href="{% static 'images/icons/apple-touch-icon-180.png' %}">
```
Al final del `<body>` (con nonce CSP):
```html
<script nonce="{{ csp_nonce }}">
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
      navigator.serviceWorker.register('/sw.js');
    });
  }
</script>
```

---

## 3. Documento de Decisión Técnica: Arquitectura Móvil y Tiendas

Se creará `docs/architecture/2026-09-30-mobile-packaging-pwa-capacitor-twa.md` documentando:

1. **Estrategia de App Única Comunitaria**:
   - Una sola ficha de app en tiendas para "I Love Voley" en lugar de gestionar docenas de fichas de club.
2. **Comparativa Técnica: PWA vs Android TWA vs Capacitor**:
   - **PWA (Elección v1)**: Inmediata, sin peajes de revisión de Apple/Google, multi-tenant natural, coste de mantenimiento nulo.
   - **Android TWA (Trusted Web Activity)**: Excelente opción para Google Play si se requiere presencia en tienda. Ejecuta la app sobre el Chrome del sistema mediante Digital Asset Links (`/.well-known/assetlinks.json`), permitiendo que Google OAuth funcione de forma nativa sin ningún bloqueo de WebView.
   - **Capacitor Shell (Opcional futuro para iOS / App Store)**:
     - **Problema de Google OAuth en WebView**: Google bloquea el login con `disallowed_useragent`.
     - **Arquitectura requerida**: No asumir sincronización mágica de cookies entre Safari y `WKWebView`. Debe utilizarse Authorization Code + PKCE mediante Custom Tabs / `ASWebAuthenticationSession` con retorno por Universal Link / deep link y canjeo mediante un endpoint de sesión seguro en Django.
     - **Riesgo de "Thin Wrapper" en Apple**: Para superar la directriz 4.2 de la App Store, la app nativa deberá incorporar valor real de dispositivo (notificaciones push APNs, acceso a cámara directa para actas/fotos, share target o biometría).

---

## 4. Plan de Testing Automatizado (`ilovevoley/core/tests/test_pwa.py`)

Siguiendo las directrices del proyecto y usando `HTTP_HOST` realista compatible con `TenantMiddleware`:
1. `test_manifest_structure_and_headers`:
   - Petición con `HTTP_HOST='ilovevoley.es'`.
   - Verifica HTTP 200, `Content-Type: application/manifest+json`, `Vary: Host`, `"id": "/"`, `name="I Love Voley"`, `short_name="ILoveVoley"` y presencia de los 3 tamaños de iconos declarados.
2. `test_manifest_tenant_theme_color`:
   - Petición con `HTTP_HOST='testclub.ilovevoley.es'`.
   - Verifica que el `theme_color` coincide con el `primary_color` del club conservando el nombre "I Love Voley".
3. `test_service_worker_headers`:
   - Verifica HTTP 200, `Content-Type: application/javascript`, `Service-Worker-Allowed: /` y cabeceras `no-cache`.
4. `test_offline_view`:
   - Verifica HTTP 200 y mensaje de desconexión.
5. `test_landing_single_membership_redirect`:
   - Usuario autenticado con 1 membresía aprobada accede a `ilovevoley.es` -> Redirige 302 a `http://testclub.ilovevoley.es/`.
6. `test_landing_multiple_memberships_no_redirect`:
   - Usuario con 2 membresías aprobadas accede a `ilovevoley.es` -> Responde 200 y pasa al contexto sus organizaciones para el selector "Tus clubes".
7. `test_templates_render_pwa_metas`:
   - Comprueba la inclusión de `rel="manifest"`, `theme-color`, `apple-touch-icon` y el script con `nonce` en `base.html` y `base_auth.html`.
