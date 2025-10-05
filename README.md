# VideosVoley

Una aplicación web Django para la gestión integral de contenido de vídeos de voleibol con capacidades avanzadas de scraping de datos de federaciones.

## Descripción

VideosVoley es una plataforma completa que permite:

- **Gestión de Vídeos**: Subir, organizar y gestionar vídeos de voleibol con integración de YouTube
- **Gestión de Imágenes**: Sistema avanzado de imágenes con etiquetado automático y moderación inteligente
- **Datos Federativos**: Scraping automático de ligas, equipos, partidos y clasificaciones desde voleibolib.net
- **Sistema de Usuarios**: Registro con Google OAuth y sistema de aprobación de usuarios
- **Vinculación Inteligente**: Conexión opcional entre vídeos/imágenes y partidos específicos
- **Categorización**: Organización por categorías y filtrado avanzado
- **Sistema de Comentarios**: Interacción entre usuarios aprobados
- **Google Vision API**: Moderación automática y etiquetado inteligente de imágenes

## Tecnologías Utilizadas

- **Backend**: Django 5.2.7 con PostgreSQL
- **Frontend**: HTML, CSS, JavaScript responsivo
- **Autenticación**: django-allauth con Google OAuth
- **IA y Visión**: Google Cloud Vision API para análisis de imágenes
- **Procesamiento de Imágenes**: Pillow para manipulación
- **Containerización**: Docker y Docker Compose
- **Scraping**: BeautifulSoup4 y requests
- **Procesamiento**: Celery para tareas asíncronas

## Configuración del Proyecto

### Requisitos Previos
- Docker y Docker Compose instalados
- Cuenta de Google para OAuth (opcional)
- Google Cloud Platform account para Vision API (opcional)

### Instalación y Configuración

1. **Clonar el repositorio**:
```bash
git clone <repository-url>
cd videosvoley
```

2. **Iniciar servicios con Docker**:
```bash
docker-compose up --build
```

3. **Configurar base de datos**:
```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

4. **Acceder a la aplicación**:
- Web: http://localhost:8000
- Admin: http://localhost:8000/admin

### Configuración de Datos

Para configurar ligas y datos federativos:

```bash
# Configurar nueva liga
docker-compose exec web python manage.py setup_league --name "Liga Name" --federation-id 1234 --season "2024-25"

# Importar todos los datos de ligas activas
docker-compose exec web python manage.py scrape_all_leagues --verbose
```

### Configuración de Google Vision API (Opcional)

Para habilitar el etiquetado automático y moderación de imágenes:

1. **Crear proyecto en Google Cloud Console**
2. **Habilitar Vision API**
3. **Crear service account y descargar clave JSON**
4. **Configurar variables de entorno**:

```bash
# En archivo .env
GOOGLE_VISION_ENABLED=true
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
AUTO_MODERATION_ENABLED=true  # Para auto-aprobación
```

### Auto-etiquetado de Imágenes

```bash
# Auto-etiquetar imágenes existentes
docker-compose exec web python manage.py autotag_images

# Procesamiento con opciones específicas
docker-compose exec web python manage.py autotag_images --limit 10 --delay 2.0
```

## Base de Datos

- **Host**: localhost:5432 (via Docker)
- **Base de datos**: volleyvideos
- **Usuario**: volleyuser
- **Contraseña**: volleypass

## Estructura del Proyecto

```
videosvoley/
├── videosvoley/
│   ├── videos/          # Gestión de vídeos, imágenes y datos federativos
│   ├── users/           # Sistema de usuarios y autenticación
│   └── settings/        # Configuración Django
├── templates/           # Plantillas HTML
├── static/             # Archivos estáticos
├── media/              # Archivos subidos (imágenes)
├── docker-compose.yml  # Configuración Docker
└── requirements.txt    # Dependencias Python
```

## Funcionalidades Principales

### Para Usuarios
- Visualización de vídeos categorizados
- Galería de imágenes con filtros avanzados
- Subida de imágenes con etiquetado automático
- Búsqueda por etiquetas y filtrado inteligente
- Sistema de comentarios
- Información detallada de ligas y partidos

### Para Administradores
- Gestión completa de vídeos e imágenes
- Sistema de moderación automática con Vision API
- Etiquetado automático y procesamiento masivo
- Scraping automático de datos federativos
- Aprobación de usuarios
- Configuración de ligas y equipos

### Datos Federativos
- Scraping automático desde voleibolib.net
- Gestión de ligas, equipos y clasificaciones
- Vinculación inteligente contenido-partido
- Actualizaciones programadas

### Sistema de Imágenes
- Subida drag & drop con validación automática
- 6 tipos de imagen: partido, celebración, entrenamiento, etc.
- Etiquetado manual y automático con Vision API
- Moderación inteligente con Google AI
- Filtros avanzados y búsqueda por etiquetas
- Imágenes independientes sin vinculación a partidos

## Comandos Útiles

```bash
# Desarrollo
docker-compose up -d                    # Iniciar en background
docker-compose down                     # Parar servicios
docker-compose exec web python manage.py shell  # Shell Django

# Testing
docker-compose exec web python manage.py test

# Scraping
docker-compose exec web python manage.py scrape_all_leagues --verbose

# Gestión de Imágenes
docker-compose exec web python manage.py autotag_images --dry-run
docker-compose exec web python manage.py autotag_images --limit 10
```

## Documentación Adicional

- **[Sistema de Imágenes](videosvoley/docs/IMAGENES.md)**: Documentación completa del sistema de gestión de imágenes
- **[Scraping de Federaciones](videosvoley/docs/SCRAPING.md)**: Guía detallada del sistema de scraping

## URLs Principales

- `/videos/` - Lista de vídeos y galería
- `/videos/imagenes/` - Galería de imágenes con filtros
- `/videos/imagenes/subir/` - Subida de imágenes
- `/videos/ligas/` - Información de ligas
- `/admin/` - Panel de administración

## Contribución

1. Fork el repositorio
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Añadir nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## Notas de Versión

### v2.0 - Sistema de Imágenes Avanzado
- ✨ Imágenes independientes sin vinculación obligatoria a partidos
- 🏷️ Sistema de etiquetado manual y automático
- 🤖 Integración con Google Vision API para moderación y etiquetado
- 🔍 Filtros avanzados por tipo, etiquetas y vinculación
- 📸 6 tipos de imagen: partido, celebración, entrenamiento, etc.
- ⚡ Comando de auto-etiquetado masivo
- 📖 Documentación completa actualizada
