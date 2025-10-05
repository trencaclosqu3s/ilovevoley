# VideosVoley

Una aplicación web Django para la gestión integral de contenido de vídeos de voleibol con capacidades avanzadas de scraping de datos de federaciones.

## Descripción

VideosVoley es una plataforma completa que permite:

- **Gestión de Vídeos**: Subir, organizar y gestionar vídeos de voleibol con integración de YouTube
- **Datos Federativos**: Scraping automático de ligas, equipos, partidos y clasificaciones desde voleibolib.net
- **Sistema de Usuarios**: Registro con Google OAuth y sistema de aprobación de usuarios
- **Vinculación Inteligente**: Conexión automática entre vídeos y partidos específicos
- **Categorización**: Organización por categorías y filtrado avanzado
- **Sistema de Comentarios**: Interacción entre usuarios aprobados

## Tecnologías Utilizadas

- **Backend**: Django 5.2.7 con PostgreSQL
- **Frontend**: HTML, CSS, JavaScript responsivo
- **Autenticación**: django-allauth con Google OAuth
- **Containerización**: Docker y Docker Compose
- **Scraping**: BeautifulSoup4 y requests
- **Procesamiento**: Celery para tareas asíncronas

## Configuración del Proyecto

### Requisitos Previos
- Docker y Docker Compose instalados
- Cuenta de Google para OAuth (opcional)

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

## Base de Datos

- **Host**: localhost:5432 (via Docker)
- **Base de datos**: volleyvideos
- **Usuario**: volleyuser
- **Contraseña**: volleypass

## Estructura del Proyecto

```
videosvoley/
├── videosvoley/
│   ├── videos/          # Gestión de vídeos y datos federativos
│   ├── users/           # Sistema de usuarios y autenticación
│   └── settings/        # Configuración Django
├── templates/           # Plantillas HTML
├── static/             # Archivos estáticos
├── docker-compose.yml  # Configuración Docker
└── requirements.txt    # Dependencias Python
```

## Funcionalidades Principales

### Para Usuarios
- Visualización de vídeos categorizados
- Búsqueda y filtrado avanzado
- Sistema de comentarios
- Información detallada de ligas y partidos

### Para Administradores
- Gestión completa de vídeos
- Scraping automático de datos federativos
- Aprobación de usuarios
- Configuración de ligas y equipos

### Datos Federativos
- Scraping automático desde voleibolib.net
- Gestión de ligas, equipos y clasificaciones
- Vinculación inteligente vídeo-partido
- Actualizaciones programadas

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
```

## Contribución

1. Fork el repositorio
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Añadir nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request
