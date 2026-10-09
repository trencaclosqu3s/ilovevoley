# Design: Página de transparencia de imagen (#222)

## Intent

Página de plataforma, en lenguaje claro, que explica a familias y jugadores **quién ve fotos e información de imagen** en la app. No sustituye la política legal (`/privacidad/`, #469). No es un portal familiar: la gestión del consentimiento vive en «Tú» y en las fichas de hijos (#122).

**Éxito:** el texto refleja el comportamiento real del código; un usuario autenticado la encuentra desde el pie; puede saltar a «Tú» para gestionar consentimientos.

## Decisiones acordadas

| Tema | Decisión |
|------|----------|
| Alcance de producto | Contenido fijo de la web (plataforma comunitaria), no CMS por club |
| PDF / impresión | Fuera de v1 (solo web) |
| Visibilidad | Solo usuarios autenticados (`@login_required`) |
| Descubrimiento | Enlace en el pie, junto a «Política de Privacidad» |
| Enfoque técnico | Hermana de `/privacidad/` en `core` (enfoque A) |
| Portal familiar / #123 / #124 | Fuera; no inventar audiencias que aún no existen |

### Desviaciones respecto al issue #222

El issue pedía textos editables por coordinador, versión imprimible/PDF y atajos al “centro familiar”. Acordado para v1:

- Sin edición por club.
- Sin PDF ni CSS de impresión dedicado.
- Atajos a `rosters:my_profile` («Tú» / hijos), no a un portal nuevo.

## Comportamiento real a reflejar (no marketing)

Fuente de verdad: `#122` y código actual.

1. **Consentimiento en `Person.image_consent`:** `none` | `internal_only` (default) | `full_public`.
2. **Galería del club:** detrás de acceso de tenant; la ven miembros con acceso al club, no el público de internet.
3. **Foto/cromo de ficha:** respeta consentimiento (`player_card`): público / solo propio o padres / no mostrar.
4. **Etiquetado y moderación:** avisos si hay fichas etiquetadas con `none`.
5. **No existe aún** distinción “solo staff del equipo” vs “resto del club”, ni portal público (#124). La página no debe prometerlo.

## Diseño técnico

### Ruta y vista

- URL: `/transparencia-imagen/`
- Name: `core:image_transparency`
- Vista: `image_transparency` en `ilovevoley/core/views.py`
- Decorador: `@login_required` (no `tenant_access_required`; el contenido es de plataforma)
- Anónimo: redirect a login (comportamiento estándar de Django)

### Template

- `ilovevoley/core/templates/core/image_transparency.html`
- Extiende `base.html`
- Tono corto y no jurídico; enlace a `core:privacy_policy` para el texto legal
- Secciones de contenido:
  1. Intro + enlace a política legal
  2. Los tres niveles de consentimiento (nombres legibles)
  3. Qué implica cada uno hoy (galería, cromo, avisos; sin promesas futuras)
  4. Cómo gestionarlo → enlace a `rosters:my_profile`
  5. Cierre con contacto de privacidad (mismo email que #469 / `PRIVACY_CONTACT_EMAIL` o fallback)

### Pie (`base.html`)

Dentro del bloque `{% if user.is_authenticated %}` donde ya está el enlace a la política:

- Nuevo enlace a `core:image_transparency`
- Copy corto (i18n), p. ej. «Quién ve las fotos» (afinable en implementación)

Sin entrada en nav principal ni bloque nuevo en «Tú».

### i18n

- Cadenas con `{% trans %}` / `{% blocktrans %}`
- `makemessages -l ca` y traducir en `locale/ca/LC_MESSAGES/django.po`

### Ficheros tocados

- `ilovevoley/core/views.py`
- `ilovevoley/core/urls.py`
- `ilovevoley/core/templates/core/image_transparency.html`
- `ilovevoley/templates/base.html`
- `locale/ca/LC_MESSAGES/django.po`
- `ilovevoley/core/tests/test_views.py` (y sweep de `reverse` si aplica, como en #469)

Sin modelos ni migraciones.

## Tests

Justificación (guía de testing): protegen decisiones de producto (acceso, descubrimiento en pie, contenido alineado con #122), no el motor de templates.

1. Anónimo en la URL → redirect a login.
2. Autenticado → 200 y fragmentos clave (tres niveles y/o enlace a «Tú»).
3. Pie: enlace ausente si anónimo, presente si autenticado (mismo patrón que `test_privacy_policy_footer_link_only_for_authenticated_users`).

No tests de clases CSS ni HTML decorativo.

## Fuera de alcance (explícito)

- Textos locales por organización
- PDF / `@media print` dedicado
- Toggles de consentimiento en esta página
- Portal familiar, portal público, audiencias futuras
- Cambiar la lógica de `#122` (solo documentarla en UI)

## Criterios de aceptación (v1)

- [ ] Usuario autenticado lee la página en `/transparencia-imagen/`
- [ ] Anónimo no la ve (login)
- [ ] El pie muestra el enlace solo con sesión
- [ ] El contenido cuadra con galería / cromo / avisos / niveles de #122
- [ ] Enlace a «Tú» para gestionar consentimiento
- [ ] Enlace a la política legal
- [ ] Traducción catalana de las cadenas nuevas
