# I Love Voley

Plataforma web Django para la gestión integral de vídeos, imágenes, competiciones federativas y plantillas de voleibol, multi-tenant por club/organización.

## Características Principales

- **Arquitectura Multi-Tenant**: Soporte para múltiples clubes y organizaciones con subdominios dedicados, colores corporativos, logotipo propio, homepage configurable (`default_home`) y vinculación directa a su club federativo (`Organization.club`).
- **Progressive Web App (PWA)**: Aplicación instalable en móvil y escritorio, soporte de temas según la identidad del club activo, precaching con Service Worker, página de fallback offline (`/offline/`) y conmutador in-app entre clubes federados sin abandonar la ventana de la aplicación (`.well-known/web-app-origin-association`).
- **Notificaciones Web Push**: Sistema de avisos web push mediante estándar VAPID (RFC 8292), con filtro de categorías de interés por usuario, entrega asíncrona vía Celery para resultados de partidos y nuevos álbumes/fotos (con debounce agrupador), registro de auditoría (`WebPushAudit`) y purga periódica.
- **Internacionalización (i18n)**: Soporte bilingüe en castellano (`es`) y catalán (`ca`) sin prefijos en la URL (`/i18n/setlang/`), persistencia de preferencia en perfil de usuario (`preferred_language`) y composición de notificaciones (emails y push) en el idioma de cada destinatario.
- **Gestión de Temporadas (`Season`)**: Modelo centralizado de temporadas (`2025-26`), temporada activa única (`is_current`), cálculo de inicio el 1 de septiembre y filtrado global uniforme en vídeos, galerías, ligas y plantillas.
- **Plantillas Deportivas (`Rosters`)**: Gestión histórica de personas, jugadores (`PlayerRole`) y cuerpo técnico (`StaffRole`) por temporada, con validación de dorsales únicos, soporte multi-rol para staff y fichas globales (`Person`) visibles en cada club por alta o por roles. Vista «Tú» con cromo descargable, vínculo cuenta ↔ ficha (propia o de hijos) aprobado por moderación y «Wrapped» de fin de temporada (`SeasonWrapped`).
- **Actas de Partido por Foto**: Lectura de actas manuales fotografiadas con Gemini para extraer alineaciones, crear fichas provisionales y montar la plantilla del equipo desde el acta.
- **Gestión de Vídeos**: Subida y organización de vídeos de YouTube, transmisiones en directo, categorización y vinculación inteligente a partidos.
- **Gestión de Imágenes**: Sistema con 6 tipos de imagen, álbumes grupales, subida drag & drop, cola de subida tolerante a mala cobertura (reintentos desde la PWA), compartir fotos desde el móvil (share target), soporte HEIC, descarga de álbumes en ZIP, etiquetado manual y automático con Google Vision API, y solicitud de retirada con página de transparencia.
- **Competiciones y Scraping Federativo**: Importación automatizada de ligas, equipos, sedes de juego (`Venue`), calendarios, actas, convocatorias, circulares y clasificaciones (voleibolib / RFEVB, pista y vóley playa) con validación estricta de marcadores según el formato de competición y avisos de cambios federativos en los partidos.
- **Portal Público y Directos**: Portal de competición sin login (`/competicion/`), línea de tiempo pública de partido por enlace (`/p/partido/<token>/`) con clips 9:16 de las jugadas y vista «Este finde» (`/finde/`) disponible offline.
- **Integración con el Marcador de Grada ([voley-scoreboard](https://github.com/trencaclosqu3s/voley-scoreboard))**: API con token Bearer (`SCOREBOARD_STREAM_TOKEN`) para que el marcador elija el partido del día, anuncie el directo de YouTube (push a los suscriptores), empuje el marcador en vivo a la ficha del partido, registre el resultado final validado, marque jugadas y cree el `Video` al terminar la emisión. Incluye la previa para el overlay del directo. Todo es best-effort: si ilovevoley no responde, el marcador sigue funcionando a mano.
- **Localización de Sedes ("¿Dónde juega el rival?")**: Módulo público (`/donde-juega/`) para consultar y buscar pabellones de juego con coordenadas GPS y enlace directo a navegación en mapas.
- **Integración con Calendarios**: Feed ICS por usuario para que el calendario de partidos se suscriba en Google Calendar, Outlook o el móvil.
- **Sistema de Usuarios y Moderación**: Autenticación Google OAuth, membresías por club (`Membership`) con roles diferenciados (`admin`, `manager`, `member`) y moderación descentralizada que permite a los managers de cada club aprobar a sus propios miembros desde `/core/moderacion/`.
- **Tema y Modo Oscuro**: Soporte nativo para modo claro y modo oscuro, respetando las preferencias del sistema.

## Tecnologías Utilizadas

- **Backend**: Python 3.13 con **Django 6.0.9** y **PostgreSQL**
- **Dependencias**: [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`)
- **Panel Admin**: **django-unfold**
- **PWA & Web Push**: Service Workers, Web App Manifest dinámico, `pywebpush` (VAPID RFC 8292)
- **Internacionalización**: Django gettext (`es` y `ca`)
- **Autenticación**: django-allauth con Google OAuth
- **IA y Visión**: Google Cloud Vision API (moderación y etiquetado) y Gemini (lectura de actas y textos narrativos)
- **Procesamiento de Imágenes**: Pillow y pillow-heif (soporte HEIC)
- **Tareas Asíncronas**: Celery con Redis y django-celery-beat
- **Suscripciones de Calendario**: django-ical (feed ICS por usuario)
- **Scraping**: BeautifulSoup4, requests y pypdf
- **Monitorización**: Sentry SDK
- **Containerización**: Docker y Docker Compose

## Configuración y Despliegue

### Requisitos Previos
- Docker y Docker Compose
- Cuenta de Google Cloud Platform (para Google OAuth y Google Vision API, opcional)

### Entorno de Desarrollo Local

1. **Clonar el repositorio**:
   ```bash
   git clone <repository-url>
   cd videosvoley
   ```

2. **Crear archivo `.env`** a partir de las variables requeridas (base de datos, credenciales, etc.).

3. **Iniciar servicios con Docker (desarrollo)**:
   ```bash
   docker compose -f docker-compose.dev.yml up -d
   ```

4. **Aplicar migraciones y crear superusuario**:
   ```bash
   docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate
   docker compose -f docker-compose.dev.yml run --rm web python manage.py createsuperuser
   ```

5. **Generar claves VAPID para Web Push (opcional en desarrollo)**:
   ```bash
   docker compose -f docker-compose.dev.yml run --rm web python manage.py generate_vapid_keys
   ```
   Copia las claves generadas a las variables `VAPID_PUBLIC_KEY` y `VAPID_PRIVATE_KEY` en tu `.env`.

6. **Acceso**:
   - Web: `http://localhost:8008` (puerto configurable con `DEV_WEB_PORT`)
   - Admin: `http://localhost:8008/<ADMIN_URL>` (ruta configurable, ver [ADMIN_URL_SEGURIDAD](ilovevoley/docs/ADMIN_URL_SEGURIDAD.md))
   - Un club concreto (tenant): `http://<subdominio>.lvh.me:8008`, arrancando `web` con `TENANT_BASE_DOMAIN=lvh.me:8008` y `ALLOWED_HOSTS=localhost,127.0.0.1,.lvh.me` (ver [AGENTS.md](AGENTS.md))

### Ejecución de Tests

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db -n auto
```

> [!NOTE]
> El flag `--create-db` es obligatorio en CI y siempre que cambien las migraciones. En iteración local, `--reuse-db` evita recrear la base de datos. `-n auto` reparte la suite entre núcleos (`pytest-xdist`).

Antes de añadir un test, revisa [`docs/ai-guidelines/testing-guidelines.md`](docs/ai-guidelines/testing-guidelines.md).

### Entorno de Producción

En el servidor de producción la aplicación corre con el compose por defecto y se despliega con:

```bash
./deploy.sh
```

El `entrypoint.sh` no ejecuta migraciones ni `collectstatic`: un despliegue manual debe hacer `git pull`, `docker compose build`, `migrate`, `collectstatic --noinput`, `compilemessages` y `up -d`, en ese orden (ver [DESPLIEGUE](ilovevoley/docs/DESPLIEGUE.md)).

> [!CAUTION]
> **No ejecutar `docker-compose.dev.yml` en producción**: resuelve al mismo nombre de proyecto compose (`videosvoley`) y reutilizaría los contenedores `db` y `redis` de producción.

## Estructura del Proyecto

El paquete principal de la aplicación es `ilovevoley`:

```
videosvoley/
├── ilovevoley/
│   ├── core/           # Multi-tenant (Organization), Season, Category, auditoría, middleware
│   ├── competitions/   # Ligas, partidos, sedes, clasificaciones, scraping, actas, portal público y feed ICS
│   ├── teams/          # Clubes oficiales, equipos y variantes (filiales/colores)
│   ├── rosters/        # Personas, jugadores, staff, vínculo cuenta↔ficha y Wrapped
│   ├── content/        # Vídeos, imágenes, comentarios y moderación Vision API
│   ├── users/          # Usuarios, membresías por club, OAuth, Web Push, feed iCal y onboarding
│   ├── videos/         # Capa de compatibilidad legada, comandos de gestión y tareas periódicas Celery
│   ├── static/         # Archivos estáticos fuente (CSS, JS, logos)
│   ├── templates/      # Plantillas organizadas por app de dominio
│   └── docs/           # Documentación técnica temática del proyecto
├── config/             # Configuración Django (settings.py, urls.py, celery.py, celery_schedule.py, sentry.py)
├── docs/               # ADRs (architecture/), specs de diseño y guías para agentes
├── locale/             # Catálogos de traducción (ca)
├── docker-compose.yml  # Configuración para producción (Nginx + Gunicorn)
├── docker-compose.dev.yml # Configuración para desarrollo local
├── pyproject.toml      # Dependencias de Python (fuente de verdad)
└── uv.lock             # Versiones exactas (transitivos + hashes)
```

Los tests viven en cada app (`ilovevoley/<app>/tests/`).

## Configuración de Ligas y Scraping

Al dar de alta una liga desde el admin (`/admin/competitions/league/add/`), el sistema autoconfigura los 3 endpoints básicos de scraping mediante signals:
1. **Clasificación**: parser `table_standings`
2. **Resultados**: parser `match_results`
3. **Calendario**: parser `match_calendar`

Las ligas de amistosos (`friendly`) no generan endpoints.

También se puede crear mediante comando de gestión:

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py setup_league \
  --name "Senior Masculino" \
  --federation-id 7998 \
  --season "2024-25" \
  --competition-type regular
```

Para ejecutar el scraping de todas las ligas activas:

```bash
docker compose -f docker-compose.dev.yml run --rm web python manage.py scrape_all_leagues --verbose
```

## URLs Principales

- `/` - Landing page y resolución contextual de tenant
- `/manifest.webmanifest` - Manifiesto PWA dinámico según tenant
- `/sw.js` - Service Worker de la PWA
- `/offline/` - Pantalla de fallback offline
- `/i18n/setlang/` - Selector dinámico de idioma (`es` / `ca`)
- `/donde-juega/` - Localizador de pistas y sedes federativas ("¿Dónde juega el rival?")
- `/finde/` - «Este finde»: partidos del fin de semana (disponible offline)
- `/competicion/` - Portal público de competición (ligas, calendario, resultados, clasificación)
- `/p/partido/<token>/` - Línea de tiempo pública de un partido
- `/videos/` o `/content/` - Lista de vídeos por categoría y temporada
- `/content/imagenes/` - Galería de imágenes y álbumes grupales
- `/content/imagenes/subir/` - Subida de imágenes con drag & drop
- `/competitions/ligas/` - Ligas y clasificaciones
- `/competitions/calendario/` - Calendario interactivo de partidos
- `/rosters/plantillas/` - Resumen y detalle de plantillas por equipo y temporada
- `/rosters/personas/yo/` - Vista «Tú»: roles, cromo, Wrapped y vínculo con fichas
- `/profile/` - Perfil, preferencias y checklist de bienvenida
- `/teams/equipos/` - Lista de equipos del club
- `/core/moderacion/` - Panel de moderación descentralizada de usuarios y membresías
- `/core/transparencia-imagen/` - Transparencia sobre el tratamiento de imágenes
- `/api/webpush/` - Endpoints de clave VAPID y suscripción a notificaciones Web Push
- `/<ADMIN_URL>` - Panel de administración (ruta configurable)

## Documentación Técnica Adicional

Para más detalles, consulta la documentación especializada en [`ilovevoley/docs/`](ilovevoley/docs/):

- **[Progressive Web App (PWA)](ilovevoley/docs/PWA.md)**: Instalación, Service Worker, caché, soporte offline y origin association multi-tenant
- **[Notificaciones Web Push](ilovevoley/docs/NOTIFICACIONES_PUSH.md)**: Arquitectura VAPID RFC 8292, suscripción, tareas Celery, debounce y auditoría
- **[Sistema Multi-Tenant](ilovevoley/docs/MULTI_TENANT.md)**: Configuración de organizaciones, subdominios, branding, homepage y cookies
- **[Temporadas y Plantillas](ilovevoley/docs/TEMPORADAS_Y_PLANTILLAS.md)**: Modelo unificado Season, identidad de personas y roles deportivos
- **[Sistema de Scraping](ilovevoley/docs/SCRAPING.md)**: Configuración de parsers federativos, sedes (`Venue`) y endpoints
- **[Sistema de Imágenes](ilovevoley/docs/IMAGENES.md)**: Subida, tipos de imagen, moderación, auto-etiquetado con Google Vision y ZIPs
- **[Tareas Periódicas Celery](ilovevoley/docs/TAREAS_PERIODICAS.md)**: Programación de tareas con Celery Beat (scraping, push, limpiezas)
- **[Sistema de Autenticación](ilovevoley/docs/AUTENTICACION.md)**: Google OAuth, rate-limiting, flujo de aprobación y membresías
- **[Notificaciones por Email](ilovevoley/docs/NOTIFICACIONES_EMAIL.md)**: Sistema de notificaciones transaccionales y moderación vía token
- **[Guía de Despliegue y CI/CD](ilovevoley/docs/DESPLIEGUE.md)**: Pipeline GitHub Actions, `deploy.sh`, gestión de estáticos y rollback
- **[Content Security Policy (CSP)](ilovevoley/docs/CSP.md)**: Cabeceras de seguridad, nonces y delegación de eventos
- **[Integración con el marcador](docs/architecture/integracion-marcador.md)**: Contrato con el marcador y el overlay del directo
- **[ADR: Plantilla por identidad y temporada](docs/architecture/2026-10-08-plantilla-por-identidad-y-temporada.md)**: Decisión sobre identidad global de `Person`
- **[Guía de tests](docs/ai-guidelines/testing-guidelines.md)**: Cuándo debe (y no debe) existir un test
- **[ADR: Empaquetado Móvil PWA/TWA/Capacitor](docs/architecture/2026-09-30-mobile-packaging-pwa-capacitor-twa.md)**: Registro de decisión técnica de la estrategia móvil
- **[Evaluación de Login Social](docs/architecture/2026-10-02-proveedores-login-social.md)**: Análisis comparativo de proveedores OAuth2
- **[Guía para Agentes y LLMs](AGENTS.md)**: Reglas de negocio, arquitectura y restricciones canónicas para asistentes IA
