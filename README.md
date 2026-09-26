# I Love Voley

Plataforma web Django para la gestión integral de vídeos, imágenes, competiciones federativas y plantillas de voleibol, multi-tenant por club/organización.

## Características Principales

- **Arquitectura Multi-Tenant**: Soporte para múltiples clubes y organizaciones con subdominios dedicados, colores corporativos, logotipo propio, homepage configurable (`default_home`) y vinculación directa a su club federativo (`Organization.club`).
- **Gestión de Temporadas (`Season`)**: Modelo centralizado de temporadas (`2025-26`), temporada activa única (`is_current`), cálculo de inicio el 1 de septiembre y filtrado global uniforme en vídeos, galerías, ligas y plantillas.
- **Plantillas Deportivas (`Rosters`)**: Gestión histórica de personas, jugadores (`PlayerRole`) y cuerpo técnico (`StaffRole`) por temporada, con validación de dorsales únicos y soporte multi-rol para staff.
- **Gestión de Vídeos**: Subida y organización de vídeos de YouTube, transmisiones en directo, categorización y vinculación inteligente a partidos.
- **Gestión de Imágenes**: Sistema con 6 tipos de imagen, álbumes grupales, subida drag & drop, soporte para formato HEIC (conversión automática), etiquetado manual y automático con Google Vision API.
- **Competiciones y Scraping Federativo**: Importación automatizada de ligas, equipos, calendarios, actas y clasificaciones (voleibolib / RFEVB) con validación estricta de marcadores de voleibol según el formato de competición.
- **Integración con Calendarios**: Feed ICS por usuario para que el calendario de partidos se suscriba en Google Calendar, Outlook o el móvil.
- **Sistema de Usuarios y Moderación**: Autenticación Google OAuth, membresías por club (`Membership`) y moderación descentralizada que permite a los managers de cada club aprobar a sus propios miembros desde `/core/moderacion/`.
- **Comentarios y Comunidad**: Interacción moderada entre usuarios aprobados.

## Tecnologías Utilizadas

- **Backend**: Python 3.13 con **Django 6.0.8** y **PostgreSQL**
- **Panel Admin**: **django-unfold**
- **Autenticación**: django-allauth con Google OAuth
- **IA y Visión**: Google Cloud Vision API
- **Procesamiento de Imágenes**: Pillow y pillow-heif (soporte HEIC)
- **Tareas Asíncronas**: Celery con Redis y django-celery-beat (16 tareas programadas)
- **Suscripciones de Calendario**: django-ical (feed ICS por usuario)
- **Scraping**: BeautifulSoup4 y requests
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

5. **Acceso**:
   - Web: `http://localhost:8000`
   - Admin: `http://localhost:8000/admin/`

### Ejecución de Tests

```bash
docker compose -f docker-compose.dev.yml run --rm web python -m pytest --create-db
```

> [!NOTE]
> El flag `--create-db` es obligatorio para garantizar que la base de datos de pruebas esté siempre sincronizada con las migraciones.

### Entorno de Producción

En el servidor de producción la aplicación corre con el compose por defecto:

```bash
docker compose up -d
```

> [!CAUTION]
> **No ejecutar `docker-compose.dev.yml` en producción**: el proyecto dev comparte el mismo nombre de red y volumen, lo que provocaría colisiones con los contenedores `db` y `redis` de producción.

## Estructura del Proyecto

El paquete principal de la aplicación es `ilovevoley`:

```
videosvoley/
├── ilovevoley/
│   ├── core/           # Multi-tenant (Organization), Season, Category, auditoría, middleware
│   ├── competitions/   # Ligas, partidos, clasificaciones, scraping y calendarios ICS
│   ├── teams/          # Clubes oficiales, equipos y variantes (filiales/colores)
│   ├── rosters/        # Personas, jugadores y staff técnico por temporada
│   ├── content/        # Vídeos, imágenes, comentarios y moderación Vision API
│   ├── users/          # Usuarios, membresías por club, OAuth y sincronización Calendar
│   ├── videos/         # Capa de compatibilidad legada y tareas periódicas Celery
│   ├── static/         # Archivos estáticos fuente (CSS, JS, logos)
│   ├── templates/      # Plantillas organizadas por app de dominio
│   └── docs/           # Documentación técnica temática del proyecto
├── config/             # Configuración Django (settings.py, urls.py, celery.py, sentry.py)
├── tests/              # Batería de pruebas automatizadas (pytest)
├── docker-compose.yml  # Configuración para producción (Nginx + Gunicorn)
├── docker-compose.dev.yml # Configuración para desarrollo local
└── requirements.txt    # Dependencias de Python
```

## Configuración de Ligas y Scraping

Al dar de alta una liga desde el admin (`/admin/competitions/league/add/`), el sistema autoconfigura los 3 endpoints básicos de scraping mediante signals:
1. **Clasificación**: parser `table_standings`
2. **Resultados**: parser `json_results` (op=2)
3. **Calendario**: parser `json_matches` (op=1)

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
- `/videos/` o `/content/` - Lista de vídeos por categoría y temporada
- `/content/imagenes/` - Galería de imágenes y álbumes
- `/content/imagenes/subir/` - Subida de imágenes con drag & drop
- `/competitions/ligas/` - Ligas y clasificaciones
- `/competitions/calendario/` - Calendario interactivo de partidos
- `/rosters/plantillas/` - Resumen y detalle de plantillas por equipo y temporada
- `/teams/equipos/` - Lista de equipos del club
- `/core/moderacion/` - Panel de moderación de usuarios y membresías
- `/admin/` - Panel de administración general

## Documentación Técnica Adicional

Para más detalles, consulta la documentación especializada en [`ilovevoley/docs/`](ilovevoley/docs/):

- **[Sistema Multi-Tenant](ilovevoley/docs/MULTI_TENANT.md)**: Configuración de organizaciones, subdominios, branding y homepage
- **[Temporadas y Plantillas](ilovevoley/docs/TEMPORADAS_Y_PLANTILLAS.md)**: Modelo unificado Season, roles de jugadores y staff técnico
- **[Sistema de Scraping](ilovevoley/docs/SCRAPING.md)**: Configuración de parsers federativos y endpoints
- **[Sistema de Imágenes](ilovevoley/docs/IMAGENES.md)**: Subida, tipos de imagen, moderación y auto-etiquetado con Google Vision
- **[Tareas Periódicas Celery](ilovevoley/docs/TAREAS_PERIODICAS.md)**: Programación de tareas con Celery Beat
- **[Sistema de Autenticación](ilovevoley/docs/AUTENTICACION.md)**: Google OAuth, flujo de aprobación y membresías
- **[Notificaciones por Email](ilovevoley/docs/NOTIFICACIONES_EMAIL.md)**: Sistema de notificaciones transaccionales y moderación vía token
- **[Guía para Agentes y LLMs](AGENTS.md)**: Reglas de negocio, arquitectura y restricciones canónicas para asistentes IA
