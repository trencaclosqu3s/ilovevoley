# Empaquetado Móvil Ligero: App Única PWA y Decisión Técnica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar la PWA oficial comunitaria "I Love Voley" (manifest dinámico, service worker estricto, iconos estándar, fallback offline, redirección inteligente de membresías y metas en plantillas base) junto con el documento de decisión técnica de empaquetado móvil (PWA vs Capacitor vs TWA y mitigación de Google OAuth).

**Architecture:** App web Django multi-tenant enriquecida con capacidades PWA: un único manifiesto W3C estandarizado servido en `/manifest.webmanifest`, un Service Worker nativo servido en `/sw.js` con cabecera `Service-Worker-Allowed: /` que aplica network-only estricto para HTML y medios protegidos con fallback offline ante cortes de red, y redirección directa en la raíz para usuarios con una sola membresía de club.

**Tech Stack:** Django 6.0.8, Python 3.12, Vanilla JavaScript (Service Worker API), Tailwind CSS, Pillow (generación de iconos), pytest.

**Spec:** [`docs/superpowers/specs/2026-09-30-pwa-empaquetado-movil-design.md`](file:///Users/jamartinmari/orca/workspaces/videosvoley/feature-producto-empaquetado-m-vil-ligero-pwa-in/docs/superpowers/specs/2026-09-30-pwa-empaquetado-movil-design.md)

## Global Constraints

- **Nombre y marca unificada**: La aplicación se denomina "I Love Voley" (`short_name: "ILoveVoley"`), compartiendo identidad visual en toda la plataforma.
- **Aislamiento multi-tenant y seguridad**: Cero almacenamiento en caché de respuestas HTML, vistas autenticadas o `/media/` privado.
- **Comandos de ejecución en desarrollo**: Los tests de Django se ejecutan en Docker mediante:
  `docker compose -f docker-compose.dev.yml run --rm web python -m pytest <path> --create-db`
- **Regla de Git**: No realizar git commit ni push automáticamente sin solicitar confirmación explícita del usuario, proponiendo la imputación de tiempo (`¿@time 1h?`) y el número de issue `#227`.

---

### Task 1: Generación de Iconos PWA Estándar (192, 512, Maskable, Apple 180)

**Files:**
- Create: `ilovevoley/static/images/icons/icon-192.png`
- Create: `ilovevoley/static/images/icons/icon-512.png`
- Create: `ilovevoley/static/images/icons/icon-maskable-512.png`
- Create: `ilovevoley/static/images/icons/apple-touch-icon-180.png`
- Create: `ilovevoley/core/tests/test_pwa_icons.py`

**Interfaces:**
- Consumes: `ilovevoley/static/images/logo_app.png` (1024×1024 px).
- Produces: Assets de icono en `ilovevoley/static/images/icons/` listos para ser referenciados en `/manifest.webmanifest` y plantillas base.

- [ ] **Step 1: Escribir el test que comprueba la existencia y dimensiones de los iconos PWA**

```python
# ilovevoley/core/tests/test_pwa_icons.py
import os
from django.test import TestCase
from django.conf import settings
from PIL import Image


class PWAIconsTest(TestCase):
    def test_icons_exist_with_correct_dimensions(self):
        icons_dir = os.path.join(settings.BASE_DIR, 'ilovevoley', 'static', 'images', 'icons')
        expected_icons = {
            'icon-192.png': (192, 192),
            'icon-512.png': (512, 512),
            'icon-maskable-512.png': (512, 512),
            'apple-touch-icon-180.png': (180, 180),
        }
        for icon_name, (width, height) in expected_icons.items():
            path = os.path.join(icons_dir, icon_name)
            self.assertTrue(os.path.exists(path), f"Falta el icono {icon_name}")
            with Image.open(path) as img:
                self.assertEqual(img.size, (width, height), f"Dimensiones incorrectas para {icon_name}")
                self.assertEqual(img.format, 'PNG', f"El icono {icon_name} debe ser PNG")
```

- [ ] **Step 2: Ejecutar el test para comprobar que falla (los iconos aún no existen)**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_icons.py --create-db`
Expected: FAIL con `AssertionError: Falta el icono icon-192.png`

- [ ] **Step 3: Generar los iconos optimizados mediante script Pillow**

Generar los 4 archivos en `ilovevoley/static/images/icons/`:
- `icon-192.png` (192×192) redimensionado con resampling Lanczos.
- `icon-512.png` (512×512) redimensionado con Lanczos.
- `icon-maskable-512.png` (512×512): lienzo cuadrado con fondo `#9B7FBF` (o blanco según contraste del logo) y el logo centrado al 80% del área (zona segura de Android maskable).
- `apple-touch-icon-180.png` (180×180) redimensionado con Lanczos.

- [ ] **Step 4: Ejecutar el test para verificar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_icons.py --create-db`
Expected: PASS (4 iconos verificados).

- [ ] **Step 5: Solicitar al usuario confirmación para commit de la tarea 1**

Preguntar al usuario: *"¿Hacemos commit de la generación de iconos PWA? Propongo `@time 20m` para la issue `#227`."*

---

### Task 2: Endpoint Dinámico `/manifest.webmanifest`

**Files:**
- Modify: `ilovevoley/core/views.py`
- Modify: `config/urls.py`
- Create: `ilovevoley/core/tests/test_pwa_manifest.py`

**Interfaces:**
- Consumes: `request.tenant` (TenantMiddleware).
- Produces: Respuesta HTTP `application/manifest+json` con estructura W3C (`id`, `name`, `icons`, `theme_color`, `start_url`).

- [ ] **Step 1: Escribir tests para el endpoint del manifest (apex y tenant)**

```python
# ilovevoley/core/tests/test_pwa_manifest.py
import json
from django.test import TestCase, RequestFactory
from django.urls import reverse
from ilovevoley.core.models import Organization
from ilovevoley.core.views import manifest_json


class PWAManifestTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.org = Organization.objects.create(
            slug='santjosep',
            name='CV Sant Josep',
            primary_color='#9B7FBF',
            is_active=True,
        )

    def test_manifest_apex_domain(self):
        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/manifest+json; charset=utf-8')
        self.assertEqual(response.headers['Vary'], 'Host')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['id'], '/')
        self.assertEqual(data['name'], 'I Love Voley')
        self.assertEqual(data['short_name'], 'ILoveVoley')
        self.assertEqual(data['start_url'], '/')
        self.assertEqual(data['scope'], '/')
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['theme_color'], '#9B7FBF')
        self.assertEqual(data['background_color'], '#ffffff')
        self.assertTrue(len(data['icons']) >= 3)

    def test_manifest_tenant_domain_uses_tenant_color(self):
        self.org.primary_color = '#FF5500'
        self.org.save()

        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='santjosep.ilovevoley.es')
        request.tenant = self.org
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['name'], 'I Love Voley')
        self.assertEqual(data['theme_color'], '#FF5500')
```

- [ ] **Step 2: Ejecutar el test para comprobar que falla**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_manifest.py --create-db`
Expected: FAIL con `ImportError: cannot import name 'manifest_json' from 'ilovevoley.core.views'`

- [ ] **Step 3: Implementar la vista `manifest_json` y registrar la URL**

En `ilovevoley/core/views.py`:
```python
def manifest_json(request):
    """Devuelve el manifiesto W3C estandarizado para la PWA comunitaria I Love Voley."""
    tenant = getattr(request, 'tenant', None)
    theme_color = tenant.primary_color if tenant and tenant.primary_color else '#9B7FBF'

    manifest_data = {
        'id': '/',
        'name': 'I Love Voley',
        'short_name': 'ILoveVoley',
        'description': 'Plataforma comunitaria de gestión, vídeos y seguimiento de voleibol',
        'lang': 'es',
        'dir': 'ltr',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'theme_color': theme_color,
        'background_color': '#ffffff',
        'icons': [
            {
                'src': '/static/images/icons/icon-192.png',
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': '/static/images/icons/icon-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': '/static/images/icons/icon-maskable-512.png',
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
    }

    response = JsonResponse(manifest_data, content_type='application/manifest+json; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    response['Vary'] = 'Host'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
```
En `config/urls.py`, añadir:
```python
path('manifest.webmanifest', manifest_json, name='manifest_json'),
```

- [ ] **Step 4: Ejecutar el test para comprobar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_manifest.py --create-db`
Expected: PASS

- [ ] **Step 5: Solicitar al usuario confirmación para commit de la tarea 2**

Preguntar al usuario: *"¿Hacemos commit del endpoint `/manifest.webmanifest`? Propongo `@time 25m` para la issue `#227`."*

---

### Task 3: Pantalla de Fallback Offline (`/offline/`)

**Files:**
- Create: `ilovevoley/templates/offline.html`
- Modify: `ilovevoley/core/views.py`
- Modify: `config/urls.py`
- Create: `ilovevoley/core/tests/test_pwa_offline.py`

**Interfaces:**
- Produces: Vista HTML pública para mostrar cuando no hay conectividad.

- [ ] **Step 1: Escribir el test para la página offline**

```python
# ilovevoley/core/tests/test_pwa_offline.py
from django.test import TestCase, RequestFactory
from ilovevoley.core.views import offline_view


class PWAOfflineTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_offline_page_renders_cleanly(self):
        request = self.factory.get('/offline/', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = offline_view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Sin conexión', content)
        self.assertIn('Reintentar', content)
```

- [ ] **Step 2: Ejecutar el test para verificar que falla**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_offline.py --create-db`
Expected: FAIL con `ImportError: cannot import name 'offline_view'`

- [ ] **Step 3: Crear plantilla `offline.html` y vista `offline_view`**

Crear `ilovevoley/templates/offline.html`:
Hereda o compone una estructura limpia con el logotipo, icono wifi desconectado, texto explicativo y botón de recarga `onclick="window.location.reload()"`.
En `ilovevoley/core/views.py`:
```python
def offline_view(request):
    """Página de fallback cuando el usuario no dispone de conexión a internet."""
    return render(request, 'offline.html', status=200)
```
En `config/urls.py`:
```python
path('offline/', offline_view, name='offline_fallback'),
```

- [ ] **Step 4: Ejecutar el test para comprobar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_offline.py --create-db`
Expected: PASS

- [ ] **Step 5: Solicitar al usuario confirmación para commit de la tarea 3**

Preguntar al usuario: *"¿Hacemos commit de la pantalla offline de la PWA? Propongo `@time 20m` para la issue `#227`."*

---

### Task 4: Service Worker (`/sw.js`) con Estrategia Estricta y URLs Raíz

**Files:**
- Create: `ilovevoley/static/js/sw.js`
- Modify: `ilovevoley/core/views.py`
- Modify: `config/urls.py`
- Create: `ilovevoley/core/tests/test_pwa_sw.py`

**Interfaces:**
- Produces: Endpoint `/sw.js` con cabecera `Service-Worker-Allowed: /`, `Content-Type: application/javascript`, `Cache-Control: no-cache, no-store, must-revalidate`.

- [ ] **Step 1: Escribir tests para el endpoint del Service Worker**

```python
# ilovevoley/core/tests/test_pwa_sw.py
from django.test import TestCase, RequestFactory
from ilovevoley.core.views import service_worker


class PWAServiceWorkerTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_service_worker_headers(self):
        request = self.factory.get('/sw.js', HTTP_HOST='ilovevoley.es')
        response = service_worker(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertEqual(response.headers['Service-Worker-Allowed'], '/')
        self.assertIn('no-cache', response.headers['Cache-Control'])
        content = response.content.decode('utf-8')
        self.assertIn('ilovevoley-pwa-v1', content)
        self.assertIn('/offline/', content)
```

- [ ] **Step 2: Ejecutar el test para comprobar que falla**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_sw.py --create-db`
Expected: FAIL con `ImportError: cannot import name 'service_worker'`

- [ ] **Step 3: Implementar `sw.js` y la vista Django `service_worker`**

Crear `ilovevoley/static/js/sw.js` con:
- `CACHE_NAME = 'ilovevoley-pwa-v1';`
- `PRECACHE_URLS = ['/offline/', '/static/css/app.css', '/static/images/icons/icon-192.png', '/static/images/icons/icon-512.png'];`
- Listener `install`: `cache.addAll(PRECACHE_URLS)`.
- Listener `activate`: eliminar caches que empiecen por `ilovevoley-pwa-` y no sean `CACHE_NAME`.
- Listener `fetch`:
  - Solo GET y same-origin.
  - Si `mode === 'navigate'`: `event.respondWith(fetch(event.request).catch(() => caches.match('/offline/')));` (sin atrapar errores 404/500, solo rechazo de red).
  - Si es `/media/`, `/protected-media/`, `/accounts/`, `/admin/`, API: `fetch(event.request)` directo sin cache.
  - Si es `/static/`: Stale-While-Revalidate o Cache-First si `response.ok`.
En `ilovevoley/core/views.py`:
```python
def service_worker(request):
    """Sirve el archivo sw.js desde la raíz con cabeceras de Service Worker."""
    sw_path = os.path.join(settings.BASE_DIR, 'ilovevoley', 'static', 'js', 'sw.js')
    with open(sw_path, 'r', encoding='utf-8') as f:
        content = f.read()
    response = HttpResponse(content, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response
```
En `config/urls.py`:
```python
path('sw.js', service_worker, name='service_worker'),
```

- [ ] **Step 4: Ejecutar el test para comprobar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_sw.py --create-db`
Expected: PASS

- [ ] **Step 5: Solicitar al usuario confirmación para commit de la tarea 4**

Preguntar al usuario: *"¿Hacemos commit del Service Worker? Propongo `@time 30m` para la issue `#227`."*

---

### Task 5: Redirección Inteligente de Membresías en `landing`

**Files:**
- Modify: `ilovevoley/core/views.py` (`landing`)
- Modify: `ilovevoley/templates/landing.html`
- Create: `ilovevoley/core/tests/test_pwa_landing_memberships.py`

**Interfaces:**
- Consumes: `request.user.memberships` (`Membership` model).
- Produces: Redirección 302 a subdominio si 1 membresía; renderizado de "Tus clubes" si >1 membresías.

- [ ] **Step 1: Escribir tests para el flujo de membresías en landing**

```python
# ilovevoley/core/tests/test_pwa_landing_memberships.py
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership

User = get_user_model()


class PWALandingMembershipsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='player', password='testpassword123')
        self.org1 = Organization.objects.create(slug='clubalpha', name='Club Alpha', is_active=True)
        self.org2 = Organization.objects.create(slug='clubbeta', name='Club Beta', is_active=True)

    def test_single_approved_membership_redirects_to_tenant(self):
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=True)
        self.client.login(username='player', password='testpassword123')

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertIn('clubalpha.', response.url)

    def test_multiple_approved_memberships_renders_landing_without_redirect(self):
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=True)
        Membership.objects.create(user=self.user, organization=self.org2, is_approved=True)
        self.client.login(username='player', password='testpassword123')

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertIn('user_organizations', response.context)
        self.assertEqual(len(response.context['user_organizations']), 2)
```

- [ ] **Step 2: Ejecutar el test para comprobar que falla**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_landing_memberships.py --create-db`
Expected: FAIL (actualmente `landing` no redirige por número de membresías).

- [ ] **Step 3: Implementar la redirección condicional en `landing` y el bloque "Tus clubes" en `landing.html`**

En `ilovevoley/core/views.py`:
```python
    if request.user.is_authenticated and not request.tenant:
        from ilovevoley.users.models import Membership
        user_memberships = list(
            Membership.objects.filter(user=request.user, is_approved=True)
            .select_related('organization')
        )
        if len(user_memberships) == 1:
            org = user_memberships[0].organization
            target_url = build_tenant_url(org.slug, request)
            return redirect(target_url)

        user_organizations = [m.organization for m in user_memberships if m.organization.is_active]
```
En `ilovevoley/templates/landing.html`:
Añadir sección destacada `{% if user_organizations %}` con título "Tus clubes" para acceso directo antes de la lista completa.

- [ ] **Step 4: Ejecutar el test para comprobar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_landing_memberships.py --create-db`
Expected: PASS

- [ ] **Step 5: Solicitar al usuario confirmación para commit de la tarea 5**

Preguntar al usuario: *"¿Hacemos commit del flujo inteligente de membresías en landing? Propongo `@time 30m` para la issue `#227`."*

---

### Task 6: Metas PWA y Registro del Service Worker en Templates Base

**Files:**
- Modify: `ilovevoley/templates/base.html`
- Modify: `ilovevoley/templates/base_auth.html`
- Create: `ilovevoley/core/tests/test_pwa_templates.py`

**Interfaces:**
- Produces: `<link rel="manifest">`, metas de color, iconos de Apple y registro de `/sw.js` seguro con nonce CSP.

- [ ] **Step 1: Escribir tests para verificar las etiquetas PWA en las plantillas base**

```python
# ilovevoley/core/tests/test_pwa_templates.py
from django.test import TestCase, Client


class PWATemplatesTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_base_template_contains_pwa_metas_and_script(self):
        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('rel="manifest"', content)
        self.assertIn('name="theme-color"', content)
        self.assertIn('apple-touch-icon-180.png', content)
        self.assertIn('apple-mobile-web-app-capable', content)
        self.assertIn("navigator.serviceWorker.register('/sw.js')", content)

    def test_base_auth_template_contains_pwa_metas(self):
        response = self.client.get('/accounts/login/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('rel="manifest"', content)
        self.assertIn('name="theme-color"', content)
        self.assertIn('apple-touch-icon-180.png', content)
```

- [ ] **Step 2: Ejecutar el test para comprobar que falla**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_templates.py --create-db`
Expected: FAIL (etiquetas PWA aún no añadidas en las plantillas).

- [ ] **Step 3: Añadir las etiquetas en `base.html` y `base_auth.html`**

En `<head>`:
```html
<link rel="manifest" href="{% url 'manifest_json' %}">
<meta name="theme-color" content="{{ tenant_color|default:'#9B7FBF' }}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="I Love Voley">
<link rel="apple-touch-icon" href="{% static 'images/icons/apple-touch-icon-180.png' %}">
```
Al final de `<body>` (con nonce CSP):
```html
<script nonce="{{ csp_nonce }}">
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('/sw.js').catch(function() {});
        });
    }
</script>
```

- [ ] **Step 4: Ejecutar el test para comprobar que pasa**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa_templates.py --create-db`
Expected: PASS

- [ ] **Step 5: Solicitar al usuario confirmación para commit de la tarea 6**

Preguntar al usuario: *"¿Hacemos commit de las etiquetas PWA y registro del Service Worker en las plantillas? Propongo `@time 25m` para la issue `#227`."*

---

### Task 7: Documento de Decisión Técnica: Empaquetado Móvil (PWA vs Capacitor vs TWA)

**Files:**
- Create: `docs/architecture/2026-09-30-mobile-packaging-pwa-capacitor-twa.md`

**Interfaces:**
- Produces: Documento de arquitectura de referencia para futuras fases de empaquetado en tiendas (Google Play y App Store).

- [ ] **Step 1: Redactar el documento de decisión técnica**

Crear `docs/architecture/2026-09-30-mobile-packaging-pwa-capacitor-twa.md` incluyendo:
1. Resumen ejecutivo y decisión de App Única Comunitaria ("I Love Voley").
2. Matriz comparativa: PWA vs Android TWA vs Capacitor.
3. Google OAuth en WebViews móviles: el bloqueo de `disallowed_useragent`, por qué no asumir cookies compartidas entre navegador y WebView, solución vía TWA (Chrome Custom Tabs nativo) y solución para Capacitor vía Authorization Code + PKCE con retorno por deep link / Universal Link.
4. Pautas para superar la directriz de calidad 4.2 ("Minimum Functionality / Thin Wrapper") de Apple antes de publicar en App Store.
5. Pautas para `assetlinks.json` en Android si se decide compilar TWA.

- [ ] **Step 2: Verificar la integridad y completitud del documento**

Verificar que cubre todos los puntos de la issue #227 y las recomendaciones del análisis técnico.

- [ ] **Step 3: Solicitar al usuario confirmación para commit de la tarea 7**

Preguntar al usuario: *"¿Hacemos commit del documento de decisión de arquitectura móvil? Propongo `@time 25m` para la issue `#227`."*

---

### Task 8: Suite Completa de Tests y Verificación Final

**Files:**
- Test: Toda la suite de PWA (`ilovevoley/core/tests/test_pwa*.py`).

- [ ] **Step 1: Ejecutar la suite completa de tests de PWA**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/test_pwa*.py --create-db`
Expected: PASS (todos los tests verdes).

- [ ] **Step 2: Ejecutar la suite general del módulo `core` para asegurar que no hay regresiones**

Run: `docker compose -f docker-compose.dev.yml run --rm web python -m pytest ilovevoley/core/tests/ --create-db`
Expected: PASS (cero regresiones en middleware, context processors o vistas).

- [ ] **Step 3: Presentar el informe de cierre al usuario**
