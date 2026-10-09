# Portal público de competición en dominio de marca

**Fecha:** 2026-10-09  
**Estado:** Propuesto para revisión  
**Issue:** [#124](https://github.com/trencaclosqu3s/ilovevoley/issues/124) (reescribir alcance: sin opt-in por organización)  
**Apps afectadas:** `ilovevoley.competitions`, `ilovevoley.core` (sitemap/robots/landing), plantillas

---

## 1. Contexto y motivación

La auditoría (M-075 / issue #124) proponía un escaparate público opt-in por club en el subdominio del tenant, con flag `Organization.public_portal_enabled`.

Ese enfoque no encaja con el producto:

- Los datos de ligas, partidos, resultados y clasificación vienen del scraping federativo y **ya son públicos**.
- El dominio de marca (`ilovevoley.es`, `request.tenant is None`) es el lugar natural para SEO e indexación.
- El tenant sigue siendo la experiencia **personalizada** del club (nuestro equipo, filtros, preferencias) detrás de membresía.

Hoy el dominio raíz solo expone landing, about y precedentes públicos acotados (`donde-juega/`, enlaces `/p/partido/<token>/`). Las vistas de competición usan `@tenant_access_required()` y, sin tenant, redirigen a landing.

---

## 2. Decisiones de producto

1. **Siempre público (sin opt-in):** no hay `public_portal_enabled` ni equivalente. Si la liga entra en el catálogo del portal, es visible en marca.
2. **Dos superficies:**
   - **Marca (raíz):** portal simple, multi-liga, sin personalización de club, anónimo OK.
   - **Tenant:** vistas actuales intactas (`@tenant_access_required`), con “nuestro club”, filtros y media solo para miembros.
3. **Históricas = temporadas anteriores:** el eje de navegación es `Season` (`resolve_season_filter` / temporada actual por defecto). Las ligas `visibility_type='historical'` se muestran al elegir esa temporada; no hay sección aparte “Históricas”.
4. **Privacidad dura en portal:** nunca vídeos, imágenes, fichas `Person`, teléfonos, emails ni stream/share del club.
5. **Enfoque A:** vistas y plantillas nuevas para el portal; no ramificar `match_detail` del tenant. Lógica repetida → helpers/services compartidos.

---

## 3. Arquitectura

### 3.1. Superficies y auth

| Host | Rutas competición | Auth |
|------|-------------------|------|
| Dominio raíz (`tenant is None`) | `/competicion/...` (portal) | Anónimo |
| `{slug}.…` (tenant) | `/competitions/...` (actual) | Login + membresía aprobada |
| Tenant + path `/competicion/...` | — | **404** (no mezclar SEO) |

### 3.2. Capas de código

- **Vistas portal:** módulo nuevo (p. ej. `competitions/portal_views.py`), sin `@tenant_access_required`, comprobando `request.tenant is None` (si hay tenant → 404).
- **URLs:** include con namespace `portal` montado en `config/urls.py` como `path('competicion/', ...)`.
- **Services/helpers:** p. ej. `competitions/services/public_portal.py` (nombre orientativo) con querysets y armado de contexto reutilizable:
  - `public_leagues(season=…)`
  - listados de partidos / standings por liga
  - helpers de JSON-LD / entradas de sitemap si la transformación no es trivial
- **Plantillas:** propias y finas bajo `competitions/portal/` (o equivalente), skin de marca (no colores del club). CTA suave a login / elegir club.
- **Tenant:** no se “abre” al anónimo; no reutilizar plantillas de detalle que ya cargan media.

### 3.3. URLs del portal

- `/competicion/` — índice (temporada + accesos)
- `/competicion/ligas/`
- `/competicion/ligas/<id>/`
- `/competicion/partidos/<id>/`
- `/competicion/calendario/`
- `/competicion/resultados/`
- `/competicion/clasificacion/`

Nombres Django: `portal:index`, `portal:league_list`, `portal:league_detail`, `portal:match_detail`, `portal:calendar`, `portal:results`, `portal:standings`.

---

## 4. Catálogo de datos

Helper `public_leagues(season)` (y derivados):

- Filtra por `league.season` (temporada resuelta; default `Season.objects.current()`).
- Incluye `visibility_type` en `main` **o** `historical`.
- Excluye `reference` y `external`.
- **No** exige `is_our_team_related` (legado single-club).
- **No** exige `is_active=True` de forma global: en temporadas pasadas muchas ligas están inactivas + historical; basta la `season` correcta.
- Amistosos (`competition_type='friendly'`) fuera por defecto.
- Partidos y standings: solo de ligas del catálogo anterior.

Páginas: solo datos federativos (equipos, fechas, sede, marcador/sets, tabla). Sin preferencias de usuario ni resalte “nuestro equipo”.

---

## 5. SEO

- Indexación solo en dominio raíz; `canonical` absoluto a raíz en cada página portal.
- Open Graph por página (`og:title` / `og:description`); imagen de marca, no logo de club.
- JSON-LD:
  - Índice/listados: `SportsOrganization` (iLoveVoley); opcional `ItemList` de ligas.
  - Partido: `SportsEvent` (fecha, sede si hay, `SportsTeam` local/visitante, resultado si finalizado).
  - Sin `Person` / `ImageObject` de jugadores.
- Ampliar `sitemap_xml`: índice portal + ligas (y partidos con tope razonable) de temporada actual; URLs siempre de raíz. Fase 2 si el volumen exige sitemap índice.
- `robots.txt`: mantener disallow de admin/cuentas/media; el portal queda bajo `Allow: /`.
- Landing: enlace visible al portal.
- Cadenas i18n `es`/`ca` (`{% trans %}`).

---

## 6. Cambios fuera de competición

- **Issue #124:** actualizar visión/alcance/criterios (marca, sin flag, históricas vía season).
- **Landing / nav marca:** enlace a `/competicion/`.
- **Sitemap** en `core.views.sitemap_xml` (o helper que alimente URLs).
- Sin migración de modelo para opt-in.

---

## 7. Testing

Justificación según `docs/ai-guidelines/testing-guidelines.md`: solo tests que protejan decisión de producto. Ubicación orientativa: `competitions/tests/test_portal.py` (+ tests del helper junto al service / `test_utils.py`).

| Caso | Riesgo / decisión | Por qué debe existir |
|------|-------------------|----------------------|
| Anónimo en raíz ve portal; mismo path en tenant → 404 | Frontera marca vs tenant | Multi-tenant / auth propia |
| Anónimo en tenant `/competitions/...` sigue exigiendo login | No abrir el tenant al publicar marca | Regresión de autorización propia |
| `public_leagues(season)`: incluye main+historical de esa season; excluye reference/external; no exige `is_our_team_related` | Catálogo por temporada | QuerySet / regla de negocio |
| Detalle partido portal sin vídeos, imágenes, persons, stream de club | Privacidad | Regla cara en producción |
| Sitemap (o helper) incluye `/competicion/...` en raíz, no subdominios | SEO solo marca | Contrato / transformación propia |
| JSON-LD de partido con `SportsEvent` y equipos (assert sobre JSON emitido) | Decisión SEO de la issue | Transformación no trivial |

**No añadir** tests que solo comprueben `status_code`, HTML cosmético, CRUD de Django, o un test por URL si listado + detalle + helpers ya cubren el riesgo.

---

## 8. Criterios de éxito

- [ ] `/competicion/...` en dominio raíz indexable sin autenticación.
- [ ] Temporadas anteriores navegables vía season (históricas = esa season).
- [ ] Cero datos personales / media en el portal.
- [ ] Tenant intacto: membresía + personalización + media solo para miembros.
- [ ] Sin campo opt-in en `Organization`.
- [ ] Issue #124 alineada con este diseño.
- [ ] Tests de la §7 presentes y justificados.

---

## 9. Fuera de alcance

- Galerías, vídeos, fichas de persona o contacto en área pública.
- Opt-in / opt-out por club.
- Abrir anónimos a `/competitions/` en el tenant.
- Sitemap masivo de todo el histórico en v1 (tope + temporada actual; resto vía navegación por season).
- Reescribir las vistas tenant para unificar plantillas con el portal.

---

## 10. Relación con #124 original

| Original (auditoría) | Este diseño |
|----------------------|-------------|
| `public_portal_enabled` en `Organization` | Eliminado; siempre público en marca |
| Páginas en subdominio del club | Páginas en dominio raíz |
| Opt-in por club | N/A |
| OG + Schema.org | Conservado (en marca) |
| Sin fotos/personas | Conservado |
