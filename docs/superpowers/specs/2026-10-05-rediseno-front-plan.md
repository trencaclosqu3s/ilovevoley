# Rediseño del front: plan de implementación

Rama: `rediseño-front` (worktree). Sin commits hasta que se pida (ver CLAUDE.md global).
Mockup de referencia: https://claude.ai/artifact/S9FcrCwUfbhEqGMz5MQoVf (lienzo privado de Claude;
tableros Escritorio, Móvil y Principios). Si el enlace no se puede abrir, el resumen de abajo basta.

## Objetivo

Aire más moderno sin ser atemporal, respetando los colores de cada tenant. **Ningún hex nuevo
hardcodeado:** todo sale de `--brand` (`Organization.primary_color`) y `--brand-dark`
(`Organization.secondary_color`), inyectados en `base.html` por `core/context_processors.py`.
Sin tercer color de acento (el amarillo `csj-yellow` fijo se deja de usar en el diseño nuevo;
el azul de Sóller nunca estuvo en el modelo). Sin cambios de modelo ni migraciones.

Tenants hoy: Sant Josep (lila/amarillo), Sóller (rojo/azul), corporativo (verde, defecto sin tenant).
Pueden llegar más: el diseño debe aguantar cualquier color primario razonable.

## Decisiones de diseño

1. **Superficies planas, borde fino:** fuera `shadow-lg` y los `border-t-4` / `border-b-4` de color.
   Tarjetas `bg-white` (dark: superficie teñida), `border` 1 px teñido, radio 20 px (`rounded-[20px]`).
2. **Fondo neutro teñido:** sustituye `bg-gradient-to-br from-purple-50 via-yellow-50 ...` por
   `color-mix(in oklab, var(--brand) 5%, #fbfaf9)` (dark: 7 % sobre `#0c0a09`).
3. **Marca con medida:** `--brand-dark` para rellenos con texto blanco (contraste ≥ 4,5:1);
   `--brand` solo en tintes, bordes y chips. Un bloque protagonista de color por pantalla.
4. **Tipografía:** Bricolage Grotesque (títulos, 500/700) + DM Sans (texto 400/500/700).
   Cifras tabulares (`tabular-nums`) en marcadores, horas y duraciones.
5. **Navegación:** escritorio = cabecera sticky translúcida con píldoras (activa = tinte de marca);
   móvil/PWA = barra inferior flotante (Vídeos, Fotos, Liga, Plantilla, Tú). Este último es un
   cambio de navegación, no solo estético: confirmar con el usuario antes de la fase 5.
6. **Sin emoji** (🏐 en footer/navbar/cabeceras): SVG de balón de marca. Movimiento solo en
   hover/press (`transition` corto, elevar 3 px en tarjetas de vídeo).

## Tokens CSS (a añadir en `base.html`, junto al bloque `:root` existente)

Derivados con `color-mix`; en `.dark` se redefinen. Nombres propuestos:

| Token | Claro | Oscuro |
|---|---|---|
| `--bg` | `color-mix(in oklab, var(--brand) 5%, #fbfaf9)` | `color-mix(in oklab, var(--brand) 7%, #0c0a09)` |
| `--surface` | `#fff` | `color-mix(in oklab, var(--brand) 6%, #1c1917)` |
| `--line` | `color-mix(in oklab, var(--brand) 14%, #e7e5e4)` | `color-mix(in oklab, var(--brand) 20%, #292524)` |
| `--tint` | `color-mix(in oklab, var(--brand) 14%, white)` | `color-mix(in oklab, var(--brand) 22%, #1c1917)` |
| `--brand-text` | `var(--brand-dark)` | `color-mix(in oklab, var(--brand) 65%, white)` |
| `--ink` / `--muted` | `#1c1917` / `#57534e` | `#fafaf9` / `#a8a29e` |

Exponerlos en `tailwind.config.js` (`colors`) como `surface`, `line`, `tint`, `brand-text`, etc.
con el mismo patrón `var(--x)` que ya usan `csj-purple`. Mantener `csj-*` hasta migrar todo
(no romper plantillas aún sin tocar). Fuentes: `fontFamily.display` y `fontFamily.sans`.

## Restricciones del proyecto que condicionan la implementación

- **CSP:** `font-src` es `'self' data:` (`config/settings.py:210`, `core/middleware.py:386`).
  **No usar Google Fonts por `<link>`**: hay que autoalojar las fuentes (woff2 en
  `ilovevoley/static/fonts/`, `@font-face` en `input.css`) y precargar solo las variables usadas.
- **CSS compilado y versionado:** `ilovevoley/static/css/app.css` está en git. Tras tocar clases
  Tailwind o `input.css`, regenerar con `python scripts/build_tailwind.py` (Tailwind 3.4.17) y
  revisar que el diff de `app.css` es el esperado.
- **Scripts inline:** CSP con nonce; todo `<style>` nuevo lleva `nonce="{{ csp_nonce }}"`.
- **i18n:** cadenas nuevas con `{% trans %}`; si se añaden, `makemessages -l ca` y traducir.
  Dentro de `<script>`, `{% trans %} as x` + `{{ x|escapejs }}`.
- **Dark mode:** `darkMode: 'class'`, gestionado por `static/js/dark_mode.js`. Cada fase se prueba en ambos.
- **Formularios:** `base.html` fuerza estilos con `!important` en inputs (borde `#e5e7eb`, focus `#9B7FBF`
  **hardcodeado**: debe pasar a `var(--brand)`; bug de tenants hoy).
- **PWA:** `theme-color` ya usa `tenant_color`. No tocar manifest ni service worker.
- **Tests:** CLAUDE.md exige justificar cualquier test según `docs/ai-guidelines/testing-guidelines.md`.
  Un rediseño de plantillas no debería necesitar tests nuevos; no escribirlos por cubrir.
- Comandos Django siempre vía `docker compose -f docker-compose.dev.yml run --rm web ...`.

## Fases (cada una deja la app funcional y se puede entregar sola)

**Fase 0: base de tokens y fuentes** (sin cambio visual aún)
- `tailwind.config.js`: colores/fuentes nuevos. `input.css`: `@font-face` + utilidades mínimas.
- `base.html`: bloque `:root` + `.dark` con los tokens; sustituir `#9B7FBF` hardcodeado del focus
  por `var(--brand)`.
- Descargar woff2 de Bricolage Grotesque y DM Sans (licencia OFL) a `static/fonts/`.
- Regenerar `app.css`. Verificar: app arranca, ninguna página cambia salvo el focus de inputs.

**Fase 1: shell** (`base.html`, `includes/navbar.html`, footer, mensajes flash)
- Fondo `--bg`, cabecera translúcida con píldoras, footer con esquinas 32 px en `--brand-dark`,
  mensajes flash sin `border-l-4`. Balón SVG en lugar de 🏐.
- Aside "Galería del club": tarjeta plana (mockup Escritorio).
- Verificar en Sant Josep, Sóller y sin tenant (corporativo), claro y oscuro, 390 px y 1360 px.

**Fase 2: vídeos** (`content/templates/content/video_list.html` y tarjeta de vídeo)
- Cabecera de página (título + "Subir vídeo"), bloque "Próximo partido" (si hay `Match` próximo
  del club; si no, se omite, no inventar contenido), chips de filtro, rejilla 3 col. con tarjetas.
- La lógica de filtros (`auto_filters.js`) no cambia; solo clases/estructura. Mantener `id`s existentes
  (`filtersSection`, `activeFiltersCount`, `.auto-filter`).

**Fase 3: fotos** (`image_gallery.html`, `album_group_images.html`, `image_detail.html`) y lightbox.

**Fase 4: competición** (`competitions/templates/...`: `league_list`, `league_detail`, `match_detail`,
`calendar`). Marcadores con cifras tabulares. Aquí el rediseño pesa más (tablas de clasificación).

**Fase 5: navegación móvil** (barra inferior). Requiere confirmación; ver decisión 5. Revisar
`pwa_nav.js` (contador de historial del botón atrás) para no romper la navegación in-app.

**Fase 6: resto** (rosters, users/perfil, core/about, moderación, auth/`base_auth.html`, emails
no: los emails se quedan como están). Barrido final: `grep` de `border-t-4|border-b-4|shadow-lg|
bg-gradient-to-br|csj-yellow|🏐` y migrar o justificar los que queden.

## Tabla de migración de clases (usada en la fase 1; reutilizar en las demás con un replace ordenado)

| Antes | Después |
|---|---|
| `bg-white dark:bg-gray-800` | `bg-surface` |
| `rounded-lg shadow-lg border-t-4 border-csj-purple ...` (tarjeta) | `rounded-3xl border border-line` (sin sombra) |
| `border-gray-200 dark:border-gray-700` / `border-gray-100 ...` | `border-line` |
| `text-gray-700 dark:text-gray-300` / `text-gray-800 ...` | `text-ink` |
| `text-gray-500 dark:text-gray-400` | `text-muted` |
| `text-csj-purple dark:text-csj-yellow` | `text-brand-text` |
| `hover:bg-gray-50/100 dark:hover:bg-gray-700` | `hover:bg-tint` |
| `bg-csj-purple hover:bg-csj-purple-dark dark:bg-csj-purple-dark ...` + `text-white` (botón) | `bg-csj-purple-dark hover:opacity-90 text-white rounded-full` |
| `bg-csj-purple/10 text-csj-purple dark:bg-csj-yellow/10 ...` (chip) | `bg-tint text-brand-text` |
| `text-purple-200` / `hover:text-csj-yellow` (sobre fondo de marca) | `text-white/80` / `hover:text-white` |
| 🏐 | `{% include 'includes/ball_icon.html' with class='...' %}` |

Los colores semánticos (verde/rojo/amarillo de éxito, error, aviso) se dejan como están.

## Verificación por fase (acordada: no declarar hecho sin esto)

1. `python scripts/build_tailwind.py` sin errores y `app.css` regenerado.
2. Levantar con `docker compose -f docker-compose.dev.yml up` y revisar con los tres colores
   (cambiar `primary_color`/`secondary_color` del tenant en admin), claro/oscuro, móvil/escritorio.
3. Contraste: texto blanco sobre `--brand-dark` ≥ 4,5:1 con los hex reales de cada tenant.
   Si un tenant nuevo no llega, oscurecer `secondary_color` en admin (o calcularlo en
   `context_processors.py`: decisión pendiente, solo si ocurre).
4. Ningún hex nuevo en plantillas ni CSS (todo `var(--...)`).
5. Suite existente: `... python -m pytest --create-db --tb=short` solo si se tocó Python.

## Estado

- [x] Mockups y plan aprobados por el usuario
- [x] Fase 0: tokens en `base.html`, fuentes autoalojadas en `static/fonts`, `tailwind.config.js`,
  `app.css` regenerado; focus de inputs y toast info ya usan `--brand`. Pendiente: revisión visual en navegador.
- [x] Fase 1 (verificada en navegador: escritorio/móvil, claro/oscuro, Sant Josep y Balears, con sesión): `base.html` (fondo `bg-page`, aside plano, footer `bg-csj-purple-dark` con
  esquinas 32 px, flash sin `border-l-4`), `includes/navbar.html` (sticky translúcida, disparadores en píldora, balón SVG vía
  `includes/ball_icon.html`), `input.css` (`h1-h3` en `font-display`). Los dropdowns de la navbar siguen igual de estructura.
  Verificado en navegador (escritorio, claro y oscuro) en `/core/quienes-somos/` con Sant Josep y Balears. Falta móvil, footer
  (no visto), páginas autenticadas (dropdowns) y `cookies_banner.html` (aún con borde superior antiguo).
  **Datos de prueba locales** (BD de desarrollo, no del repo): usuario `dev_preview` (sin contraseña, admin aprobado en santjosep y
  balears) y 2 vídeos demo por club. Sesión: crear `SessionStore` por shell y fijar la cookie `sessionid` con `domain=.lvh.me`.
  **Entorno local:** el build de Docker falla con rutas con `ñ` (`rediseño-front`): usar `up -d --no-build web` (imagen
  `rediseo-front-web` ya existe). Para ver tenants hace falta un dominio de 3 niveles: `http://santjosep.lvh.me:8008` con
  override de compose (`TENANT_BASE_DOMAIN=lvh.me:8008`, `ALLOWED_HOSTS=localhost,127.0.0.1,.lvh.me`) vía `-f` extra, sin tocar
  `docker-compose.dev.yml`. Con `*.localhost` el middleware no resuelve tenant (toma `host == root_domain`).
  Nota: `Organization.secondary_color` de Balears es azul (`#003DA5`), no un rojo oscuro: `--brand-dark` = azul ahí.
- [x] Fase 2: `content/video_list.html` y `cookies_banner.html` migrados con la tabla de clases; tarjetas de vídeo con
  borde fino y radio 20 (siguen siendo iframes de YouTube, 2 columnas); inputs/selects de `base.html` ahora usan
  `--surface/--line/--ink`; navbar sin desbordamiento a ~1150 px (textos "Cambiar de club"/usuario solo desde `xl`);
  aside `lg:w-80`. **Decisión:** NO se añadió el bloque "Próximo partido" ni chips de filtro del mockup: exigen cambios de
  vista/JS y el mockup suponía miniaturas que el modelo no tiene. Pendiente si se quiere.
- [x] Fase 3: `image_gallery`, `album_group_images`, `image_detail`, `match_images`, `image_upload`, `image_bulk_upload`,
  `image_moderate/_moderation` migradas. Lightbox (`static/js/lightbox.js`) se deja: es un overlay negro fijo sin color de tenant.
  Verificado en navegador claro (Sant Josep y Balears); oscuro de la galería sin revisar. Pendiente menor: la rejilla individual
  queda como tarjeta dentro de tarjeta (borde doble), valorar quitar el contenedor externo.
  **Script de migración reutilizable** (fuera del repo, en el scratchpad de la sesión): dos pasos de `str.replace` ordenados
  (patrones específicos de tarjeta/botón antes que los genéricos de `text-gray-*`). Ojo: al migrar, buscar `querySelector` que dependan
  de clases cambiadas (p. ej. `.text-gray-600` en `image_upload.html`, ya actualizado a `.text-muted`).
- [x] Fase 4 (parcial en verificación): todas las plantillas de `competitions/templates/competitions/` migradas con regex de tokens
  (cabeceras con degradado → `bg-csj-purple-dark` plano, botones amarillos → `bg-csj-purple-dark text-white`, 🏐 → icono SVG salvo dentro
  de template literals JS de `calendar.html`). JS que alternaba clases (tabs de `league_detail`, selector de estilo de tarjeta y chips de
  `match_detail`) actualizado a las clases nuevas. Plantillas compilan. Verificado en navegador solo calendario y clasificación **vacíos**
  (oscuro); NO revisadas con datos: `league_detail`, `match_detail`, `standings` con equipos, `league_list`, `calendar` con partidos.
  La BD `videosvoley-db-1` (espejo de producción) tiene el esquema antiguo (`videos_league`, `videos_match`): usarla exigiría `migrate`
  sobre ella; no se ha tocado. Quedan emojis en títulos (📅 🏆 📋 …) a decidir en la fase 6.
- [ ] Fase 5 (pendiente de confirmar barra inferior)
- [ ] Fase 6

Otro agente: leer este fichero, `ilovevoley/templates/base.html` y `tailwind.config.js`, marcar aquí
cada fase al terminarla, y no hacer commit sin pedirlo (`@time` e issue `#NNN` antes de cada commit).
