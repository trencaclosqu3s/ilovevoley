# Content Security Policy (CSP)

## Estado

La CSP se emite en modo **enforce** (`Content-Security-Policy`), no en
`Report-Only`. La política estricta se define en `SECURE_CSP`
(`config/settings.py`) y la aplica
`django.middleware.csp.ContentSecurityPolicyMiddleware` (Django 6.0).

```python
SECURE_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.NONCE, 'https://cdn.jsdelivr.net', 'https://cdnjs.cloudflare.com'],
    'style-src':  [CSP.SELF, CSP.NONCE, 'https://cdn.jsdelivr.net', 'https://cdnjs.cloudflare.com'],
    'img-src':    [CSP.SELF, 'data:', 'blob:', 'https://*.googleusercontent.com', 'https://img.youtube.com', 'https://i.ytimg.com'],
    'font-src':   [CSP.SELF, 'data:'],
    'frame-src':  [CSP.SELF, 'https://www.youtube.com', 'https://www.youtube-nocookie.com'],
    'connect-src': [CSP.SELF],
    'object-src': [CSP.NONE],
    'base-uri':   [CSP.NONE],
    'form-action': [CSP.SELF, 'https://accounts.google.com'],
    'frame-ancestors': [CSP.NONE],
}
SECURE_CSP_REPORT_ONLY = None
```

No se usa `'unsafe-inline'` ni `'unsafe-eval'` en el sitio público. Los
scripts/estilos inline se autorizan con un **nonce por petición**.

## Nonce en plantillas

El context processor `django.template.context_processors.csp` expone
`csp_nonce`. Cualquier `<script>` o `<style>` inline debe llevarlo:

```html
<script nonce="{{ csp_nonce }}"> /* ... */ </script>
<style nonce="{{ csp_nonce }}"> /* ... */ </style>
```

Al acceder a `csp_nonce` en la plantilla se genera el nonce y Django lo
inserta en la cabecera de esa respuesta. Si una página no lo usa, la directiva
queda sin nonce, pero la política sigue siendo válida.

## Handlers inline: `csp_actions.js`

No se permiten atributos `on*=`. En su lugar, `static/js/csp_actions.js`
(servido desde `'self'`, sin nonce) actúa por delegación de eventos sobre
atributos `data-*`:

| Atributo | Efecto |
| --- | --- |
| `data-call="fn"` | Llama a `window.fn(...)` |
| `data-call-args='[1,"a"]'` | Argumentos JSON (escapar texto con `escapejs`) |
| `data-call-this` | Añade el propio elemento como último argumento |
| `data-call-prevent` | `event.preventDefault()` antes de llamar |
| `data-href="/ruta"` | Navega al hacer clic |
| `data-action="back\|reload\|dismiss-closest"` | Acciones genéricas (`data-dismiss-selector` para la última) |
| `data-submit-on-change` | Envía el formulario del control |
| `data-hide-on-error` | Oculta la imagen si falla la carga |

Ejemplo:

```html
<button data-call="openResultModal"
        data-call-args='[{{ match.id }}, "{{ match.home_team_display|escapejs }}", "{{ match.away_team_display|escapejs }}"]'>
```

El JS definido en bloques inline sigue siendo global (las funciones
declaradas se exponen en `window`), por lo que `data-call` las encuentra.

## Excepciones documentadas

1. **Panel de administración (`/admin/`)**: Unfold y Alpine.js evalúan
   expresiones con `new Function` y sus plantillas inyectan `<script>`/`<style>`
   sin nonce. `ilovevoley.core.middleware.AdminCSPMiddleware` aplica una
   política relajada (`'unsafe-inline'`, `'unsafe-eval'`) solo a las rutas del
   admin. Está acotada a usuarios de staff.
2. **Emails**: las plantillas de `*/templates/emails/` no se sirven como
   página; su HTML no pasa por esta CSP.
3. **CDNs** `cdn.jsdelivr.net` (Notyf) y `cdnjs.cloudflare.com` (Cropper.js)
   siguen permitidos en `script-src`/`style-src`. Pendiente valorar
   self-hosting para poder retirarlos.
4. **Panel del admin de `django_celery_beat`** comparte la política relajada
   del admin por estar bajo la misma URL.
5. **Login Social (`form-action`)**: `https://accounts.google.com` está
   autorizado en `form-action` para permitir la redirección POST del flujo de
   autenticación Google OAuth.

## Pendientes

- [ ] Endpoint de reportes CSP (`report-to`/`report-uri`) + colector para
      detectar violaciones en producción antes de futuros endurecimientos.
- [ ] Self-hosting de Notyf y Cropper.js para eliminar orígenes CDN.
- [ ] Evaluar `'strict-dynamic'` una vez eliminados los CDN.

## Verificación

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest \
  ilovevoley/core/tests/test_security_headers.py \
  ilovevoley/core/tests/test_csp_templates.py --create-db
```

`test_csp_templates.py` recorre las plantillas públicas y falla si aparece un
`on*=`, un `style=` inline o un `<script>`/`<style>` sin nonce.
