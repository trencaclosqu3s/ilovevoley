# 📋 Plan de Refactorización - VideosVoley

## 🎯 **Objetivo**
Refactorizar la app monolítica `videos` en múltiples apps especializadas para mejorar la mantenibilidad, escalabilidad y organización del código.

## 📊 **Estado Actual del Proyecto**

### **Problema Identificado**
- La app `videos` ha crecido orgánicamente y ahora contiene 1,264 líneas en `models.py`
- Incluye funcionalidades muy diversas: videos, fotos, partidos, equipos, clubs, plantillas, jugadores, staff
- Falta de separación clara de responsabilidades
- Dificultad para mantener y escalar el código

### **Estructura Actual**
```
videosvoley/
├── videos/           # App monolítica (1,264 líneas en models.py)
│   ├── models.py     # Contiene TODOS los modelos
│   ├── views.py      # Todas las vistas
│   ├── admin.py      # Todas las interfaces de admin
│   ├── forms.py      # Todos los formularios
│   ├── urls.py       # Todas las URLs
│   └── management/   # Todos los comandos
├── users/            # Gestión de usuarios
├── core/             # Funcionalidad compartida
└── rag/              # Sistema RAG
```

## 🏗️ **Nueva Estructura Propuesta**

### **Apps Especializadas**
1. **`content`** - Gestión de contenido multimedia
   - Videos, Imágenes, Comentarios, Categorías
   - Moderación de contenido, etiquetado automático
   
2. **`competitions`** - Gestión de competiciones
   - Ligas, Partidos, Clasificaciones, Endpoints de scraping
   
3. **`teams`** - Gestión de equipos y clubs
   - Clubs, Equipos, Logos, Información de contacto
   
4. **`rosters`** - Gestión de plantillas
   - Personas, Roles de jugadores, Roles de staff

## 📋 **Plan de Migración Detallado**

### **FASE 1: Preparación y Creación de Apps** ✅ EN PROGRESO

#### ✅ **FASE 1.1 - Crear app content** ✅ COMPLETADA
- **Estado**: ✅ COMPLETADA
- **Fecha**: 2025-01-27
- **Archivos creados**:
  - `videosvoley/content/apps.py` - Configuración de la app
  - `videosvoley/content/models.py` - Modelos: Video, Comment, Image, Category
  - `videosvoley/content/admin.py` - Interfaces de administración
  - `videosvoley/content/views.py` - Vistas básicas para contenido
  - `videosvoley/content/urls.py` - URLs de la app
  - `videosvoley/content/forms.py` - Formularios para contenido
  - `videosvoley/content/signals.py` - Señales de Django
  - `videosvoley/content/utils.py` - Utilidades para procesamiento de imágenes
  - `videosvoley/content/tests.py` - Tests unitarios
  - `videosvoley/content/management/commands/migrate_content_data.py` - Comando de migración
- **Configuración**:
  - ✅ App agregada a `INSTALLED_APPS` en `settings.py`
  - ✅ Migraciones creadas exitosamente
  - ✅ `related_name` únicos para evitar conflictos
  - ✅ Foreign keys temporales a `videos.Match` (se actualizarán después)
- **Modelos migrados**:
  - **Category**: Categorías para organizar contenido
  - **Video**: Videos de YouTube con funcionalidades completas
  - **Comment**: Sistema de comentarios
  - **Image**: Gestión avanzada de imágenes con moderación

#### ✅ **FASE 1.2 - Crear app competitions** ✅ COMPLETADA
- **Estado**: ✅ COMPLETADA
- **Modelos migrados**: League, Match, Standing, ScrapingEndpoint
- **Funcionalidades**: Gestión de competiciones, scraping de datos, admin interfaces
- **Archivos creados**: models.py, admin.py, views.py, urls.py, forms.py, signals.py, utils.py, tests.py
- **Migraciones**: Creadas exitosamente
- **Foreign keys**: Temporales a videos.Team (se actualizarán en FASE 2.7)

#### ✅ **FASE 1.3 - Crear app teams** ✅ COMPLETADA
- **Estado**: ✅ COMPLETADA
- **Modelos migrados**: Team, Club
- **Funcionalidades**: Gestión de equipos y clubs, estadísticas, búsqueda
- **Archivos creados**: models.py, admin.py, views.py, urls.py, forms.py, signals.py, utils.py, tests.py
- **Migraciones**: Creadas exitosamente
- **Foreign keys**: Temporales a content.Category (se actualizarán en FASE 2.7)

#### ✅ **FASE 1.4 - Crear app rosters** ✅ COMPLETADA
- **Estado**: ✅ COMPLETADA
- **Modelos migrados**: Person, PlayerRole, StaffRole
- **Funcionalidades**: Gestión de plantillas y roles, estadísticas, exportación
- **Archivos creados**: models.py, admin.py, views.py, urls.py, forms.py, signals.py, utils.py, tests.py
- **Migraciones**: Creadas exitosamente
- **Foreign keys**: Temporales a videos.Team (se actualizarán en FASE 2.7)

### **FASE 2: Migración de Datos** ⏳ PENDIENTE

#### 🔄 **FASE 2.1 - Crear backup completo de la base de datos** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE
- **Acciones**: Backup con `pg_dump` y `dumpdata`

#### 🔄 **FASE 2.2 - Migrar modelos de content** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE
- **Comando**: `python manage.py migrate_content_data`

#### 🔄 **FASE 2.3 - Migrar modelos de teams** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 2.4 - Migrar modelos de competitions** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 2.5 - Migrar modelos de rosters** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 2.6 - Crear scripts de migración de datos con foreign keys temporales** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 2.7 - Actualizar todas las foreign keys para apuntar a las nuevas apps** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

### **FASE 3: Migración de Código** ⏳ PENDIENTE

#### 🔄 **FASE 3.1 - Migrar views de content** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE
- **Views**: video_list, video_detail, image_gallery, image_upload

#### 🔄 **FASE 3.2 - Migrar views de competitions** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE
- **Views**: league_list, match_detail, calendar, standings

#### 🔄 **FASE 3.3 - Migrar views de teams** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE
- **Views**: team_list, team_roster, club_detail

#### 🔄 **FASE 3.4 - Migrar views de rosters** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE
- **Views**: roster management, person forms

#### 🔄 **FASE 3.5 - Migrar y distribuir forms por las nuevas apps** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 3.6 - Reorganizar URLs por dominio funcional** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 3.7 - Mover y actualizar templates por app** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 3.8 - Separar interfaces de admin por app** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 3.9 - Distribuir management commands por funcionalidad** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 3.10 - Migrar tareas de Celery por app** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

### **FASE 4: Configuración y Testing** ⏳ PENDIENTE

#### 🔄 **FASE 4.1 - Actualizar INSTALLED_APPS y configuraciones en settings.py** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 4.2 - Verificar integridad de datos migrados** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 4.3 - Probar toda la funcionalidad en las nuevas apps** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 4.4 - Actualizar todos los imports en el código** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

### **FASE 5: Limpieza** ⏳ PENDIENTE

#### 🔄 **FASE 5.1 - Eliminar modelos obsoletos de la app videos** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 5.2 - Marcar modelos Player/Staff como deprecated** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 5.3 - Limpiar migraciones temporales y de mapeo** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 5.4 - Actualizar documentación y README** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

### **FASE 6: Despliegue** ⏳ PENDIENTE

#### 🔄 **FASE 6.1 - Testing final completo del sistema** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

#### 🔄 **FASE 6.2 - Despliegue en producción con rollback plan** ⏳ PENDIENTE
- **Estado**: ⏳ PENDIENTE

## 🔧 **Estrategia de Migración de Datos**

### **Método Recomendado: Foreign Keys Temporales**
1. **Crear nuevas apps** con modelos que apunten a tablas existentes usando `db_table`
2. **Crear migraciones vacías** que no modifiquen la estructura
3. **Migrar datos** usando scripts personalizados
4. **Actualizar foreign keys** para apuntar a las nuevas apps
5. **Limpiar** modelos obsoletos

### **Plan de Rollback**
- Backup completo de la base de datos antes de cada fase
- Migraciones reversibles
- Scripts de rollback preparados
- Testing exhaustivo en cada paso

## 📁 **Estructura de Archivos Actual**

### **App Content (✅ COMPLETADA)**
```
videosvoley/content/
├── __init__.py
├── apps.py                    # ✅ Configuración de la app
├── models.py                  # ✅ Video, Comment, Image, Category
├── admin.py                   # ✅ Interfaces de administración
├── views.py                   # ✅ Vistas básicas
├── urls.py                    # ✅ URLs de la app
├── forms.py                   # ✅ Formularios
├── signals.py                 # ✅ Señales de Django
├── utils.py                   # ✅ Utilidades
├── tests.py                   # ✅ Tests unitarios
├── migrations/
│   └── 0001_initial.py       # ✅ Migración inicial
└── management/
    └── commands/
        └── migrate_content_data.py  # ✅ Comando de migración
```

### **App Videos (Original - A migrar)**
```
videosvoley/videos/
├── models.py                  # 1,264 líneas - TODOS los modelos
├── views.py                   # Todas las vistas
├── admin.py                   # Todas las interfaces de admin
├── forms.py                   # Todos los formularios
├── urls.py                    # Todas las URLs
├── tasks.py                   # Tareas de Celery
├── signals.py                 # Señales
├── utils.py                   # Utilidades
├── scraping.py                # Lógica de scraping
├── calendar_feed.py           # Feed de calendario
├── management/commands/       # Todos los comandos
└── migrations/                # Historial de migraciones
```

## 🚨 **Consideraciones Importantes**

### **Foreign Keys Temporales**
- Los modelos de `content` actualmente apuntan a `videos.Match`
- Se actualizarán a `competitions.Match` cuando se cree esa app
- Esto permite mantener la funcionalidad durante la migración

### **Related Names Únicos**
- `content_videos` para Video.created_by
- `content_comments` para Comment.user
- `content_uploaded_images` para Image.uploaded_by
- `content_moderated_images` para Image.moderated_by
- `content_videos` para Video.match
- `content_images` para Image.match

### **Dependencias**
- La app `content` depende temporalmente de `videos.Match`
- Se actualizará cuando se cree la app `competitions`
- Las otras apps seguirán el mismo patrón

## 📊 **Métricas de Progreso**

- **Fase 1**: 1/4 completada (25%)
- **Fase 2**: 0/7 completada (0%)
- **Fase 3**: 0/10 completada (0%)
- **Fase 4**: 0/4 completada (0%)
- **Fase 5**: 0/4 completada (0%)
- **Fase 6**: 0/2 completada (0%)

**Progreso Total**: 1/31 tareas completadas (3.2%)

## 🎯 **Próximos Pasos Inmediatos**

1. **FASE 1.2** - Crear app `competitions` con estructura básica
2. **FASE 1.3** - Crear app `teams` con estructura básica  
3. **FASE 1.4** - Crear app `rosters` con estructura básica
4. **FASE 2.1** - Crear backup completo de la base de datos

## 🚀 **Guía de Continuación para Nuevos Agentes**

### **Contexto del Proyecto**
- **Proyecto**: VideosVoley - Aplicación Django para gestión de contenido de voleibol
- **Problema**: App monolítica `videos` con 1,264 líneas en `models.py`
- **Solución**: Refactorizar en 4 apps especializadas
- **Estado actual**: FASE 1.4 completada - Apps `content`, `competitions`, `teams` y `rosters` creadas

### **Configuración del Entorno**
```bash
# Directorio del proyecto
cd /Users/jamartinmari/PycharmProjects/videosvoley

# Comandos Docker (usar SIEMPRE Docker)
docker-compose exec web python manage.py [comando]
docker-compose exec web python manage.py makemigrations
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py startapp nombre_app
```

### **Estructura de Base de Datos Actual**
- **PostgreSQL** en Docker
- **Host**: `db:5432` (desde dentro del contenedor)
- **Database**: `volleyvideos`
- **User**: `volleyuser`
- **Password**: `volleypass`

### **Apps Existentes y su Estado**
1. **`videosvoley.core`** - ✅ Funcionalidad compartida
2. **`videosvoley.users`** - ✅ Gestión de usuarios
3. **`videosvoley.rag`** - ✅ Sistema RAG
4. **`videosvoley.videos`** - ⚠️ App monolítica (A MIGRAR)
5. **`videosvoley.content`** - ✅ NUEVA - Creada en FASE 1.1
6. **`videosvoley.competitions`** - ✅ NUEVA - Creada en FASE 1.2
7. **`videosvoley.teams`** - ✅ NUEVA - Creada en FASE 1.3
8. **`videosvoley.rosters`** - ✅ NUEVA - Creada en FASE 1.4

### **Modelos por Migrar (desde videos a nuevas apps)**

#### **Desde videos.models a content.models** ✅ COMPLETADO
- `Category` → `content.Category`
- `Video` → `content.Video`
- `Comment` → `content.Comment`
- `Image` → `content.Image`

#### **Desde videos.models a competitions.models** ⏳ PENDIENTE
- `League` → `competitions.League`
- `Match` → `competitions.Match`
- `Standing` → `competitions.Standing`
- `ScrapingEndpoint` → `competitions.ScrapingEndpoint`

#### **Desde videos.models a teams.models** ⏳ PENDIENTE
- `Club` → `teams.Club`
- `Team` → `teams.Team`

#### **Desde videos.models a rosters.models** ⏳ PENDIENTE
- `Person` → `rosters.Person`
- `PlayerRole` → `rosters.PlayerRole`
- `StaffRole` → `rosters.StaffRole`

### **Foreign Keys Temporales Actuales**
```python
# En content.models
match = models.ForeignKey('videos.Match', ...)  # Temporal
# Se actualizará a 'competitions.Match' cuando se cree esa app
```

### **Related Names Únicos (para evitar conflictos)**
```python
# Content app
Video.created_by → related_name='content_videos'
Comment.user → related_name='content_comments'
Image.uploaded_by → related_name='content_uploaded_images'
Image.moderated_by → related_name='content_moderated_images'
Video.match → related_name='content_videos'
Image.match → related_name='content_images'
```

### **Archivos de Configuración Importantes**
- **Settings**: `config/settings.py` - INSTALLED_APPS actualizado
- **URLs principales**: `config/urls.py`
- **Docker**: `docker-compose.yml`, `docker-compose.dev.yml`

### **Comandos de Migración de Datos**
```bash
# Migrar datos de content (ya creado)
docker-compose exec web python manage.py migrate_content_data --dry-run

# Crear backup de BD
docker-compose exec web python manage.py dumpdata > backup_before_migration.json
```

### **Estrategia de Testing**
- **Dry-run**: Siempre usar `--dry-run` primero
- **Backup**: Crear backup antes de cada fase
- **Verificación**: Probar funcionalidad después de cada migración

### **Problemas Conocidos y Soluciones**
1. **Conflictos de related_name**: Usar nombres únicos por app
2. **Foreign keys temporales**: Apuntar a apps existentes durante migración
3. **Dependencias circulares**: Migrar en orden: content → teams → competitions → rosters

### **Orden de Creación de Apps**
1. ✅ **content** (COMPLETADA)
2. ⏳ **teams** (siguiente)
3. ⏳ **competitions** (después de teams)
4. ⏳ **rosters** (última)

### **Verificación de Estado**
```bash
# Verificar apps instaladas
docker-compose exec web python manage.py shell
>>> from django.apps import apps
>>> [app.label for app in apps.get_app_configs()]

# Verificar migraciones
docker-compose exec web python manage.py showmigrations

# Verificar modelos
docker-compose exec web python manage.py shell
>>> from videosvoley.content.models import Video, Comment, Image, Category
>>> print("Content models OK")
```

### **Estructura de Archivos por App (Template)**
```
videosvoley/nombre_app/
├── __init__.py
├── apps.py                    # Configuración de la app
├── models.py                  # Modelos de la app
├── admin.py                   # Interfaces de administración
├── views.py                   # Vistas
├── urls.py                    # URLs de la app
├── forms.py                   # Formularios
├── signals.py                 # Señales de Django
├── utils.py                   # Utilidades
├── tests.py                   # Tests unitarios
├── migrations/
│   └── 0001_initial.py       # Migración inicial
└── management/
    └── commands/
        └── migrate_nombre_app_data.py  # Comando de migración
```

### **Checklist para Cada Nueva App**
- [ ] Crear app con `startapp`
- [ ] Configurar `apps.py`
- [ ] Crear modelos con `related_name` únicos
- [ ] Crear `admin.py` con interfaces
- [ ] Crear `views.py` básico
- [ ] Crear `urls.py`
- [ ] Crear `forms.py`
- [ ] Crear `signals.py`
- [ ] Crear `utils.py`
- [ ] Crear `tests.py`
- [ ] Crear comando de migración en `management/commands/`
- [ ] Agregar a `INSTALLED_APPS` en `settings.py`
- [ ] Crear migraciones con `makemigrations`
- [ ] Probar migraciones con `migrate`

### **Detalles de Modelos por Migrar**

#### **Teams App (FASE 1.3)**
```python
# Desde videos.models.Club
class Club(models.Model):
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to='club_logos/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

# Desde videos.models.Team
class Team(models.Model):
    name = models.CharField(max_length=200)
    club = models.ForeignKey(Club, on_delete=models.CASCADE, related_name='teams')
    category = models.ForeignKey('content.Category', on_delete=models.CASCADE)
    season = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

#### **Competitions App (FASE 1.4)**
```python
# Desde videos.models.League
class League(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey('content.Category', on_delete=models.CASCADE)
    season = models.CharField(max_length=20)
    federation_id = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

# Desde videos.models.Match
class Match(models.Model):
    home_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='away_matches')
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches')
    match_date = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    # ... más campos
```

#### **Rosters App (FASE 1.5)**
```python
# Desde videos.models.Person
class Person(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='people/', blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

# Desde videos.models.PlayerRole
class PlayerRole(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='player_roles')
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='player_roles')
    jersey_number = models.PositiveIntegerField()
    position = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### **Dependencias Entre Apps**
```
content (✅ COMPLETADA)
    ↓
teams (⏳ SIGUIENTE)
    ↓
competitions (⏳ DESPUÉS)
    ↓
rosters (⏳ ÚLTIMA)
```

### **Foreign Keys que se Actualizarán**
```python
# Actual (temporal)
content.Video.match → videos.Match
content.Image.match → videos.Match

# Después de crear competitions
content.Video.match → competitions.Match
content.Image.match → competitions.Match

# Después de crear teams
competitions.Match.home_team → teams.Team
competitions.Match.away_team → teams.Team
rosters.PlayerRole.team → teams.Team
rosters.StaffRole.team → teams.Team
```

### **Comandos de Verificación Post-Migración**
```bash
# Verificar que no hay conflictos de related_name
docker-compose exec web python manage.py check

# Verificar migraciones
docker-compose exec web python manage.py showmigrations

# Verificar que los modelos se pueden importar
docker-compose exec web python manage.py shell
>>> from videosvoley.teams.models import Club, Team
>>> from videosvoley.competitions.models import League, Match
>>> from videosvoley.rosters.models import Person, PlayerRole
>>> print("Todos los modelos OK")
```

### **Archivos de Referencia Importantes**
- **Modelos originales**: `videosvoley/videos/models.py` (1,264 líneas)
- **Admin original**: `videosvoley/videos/admin.py`
- **Views originales**: `videosvoley/videos/views.py`
- **Forms originales**: `videosvoley/videos/forms.py`
- **URLs originales**: `videosvoley/videos/urls.py`

### **Estrategia de Rollback**
```bash
# Si algo sale mal, restaurar desde backup
docker-compose exec web python manage.py loaddata backup_before_migration.json

# O restaurar desde pg_dump
docker-compose exec -T db psql -U volleyuser -d volleyvideos < backup.sql
```

## 📝 **Notas de Desarrollo**

### **Comandos Útiles**
```bash
# Crear nueva app
docker-compose exec web python manage.py startapp nombre_app

# Crear migraciones
docker-compose exec web python manage.py makemigrations nombre_app

# Aplicar migraciones
docker-compose exec web python manage.py migrate

# Ejecutar comando de migración de datos
docker-compose exec web python manage.py migrate_content_data --dry-run
```

### **Estructura de Modelos por App**

#### **Content App**
- `Category`: Categorías para organizar contenido
- `Video`: Videos de YouTube con funcionalidades completas
- `Comment`: Sistema de comentarios
- `Image`: Gestión avanzada de imágenes con moderación

#### **Competitions App (Pendiente)**
- `League`: Ligas de voleibol
- `Match`: Partidos individuales
- `Standing`: Clasificaciones de ligas
- `ScrapingEndpoint`: Endpoints para scraping de datos

#### **Teams App (Pendiente)**
- `Club`: Clubs de voleibol
- `Team`: Equipos específicos

#### **Rosters App (Pendiente)**
- `Person`: Personas (base para jugadores y staff)
- `PlayerRole`: Roles de jugadores en equipos
- `StaffRole`: Roles de staff en equipos

---

## ⚠️ **IMPORTANTE PARA AGENTES FUTUROS**

**🔔 ACTUALIZACIÓN OBLIGATORIA**: Este documento DEBE actualizarse al completar cada fase. Incluye:
- Estado actual del progreso
- Próximo paso a realizar
- Fecha de última actualización
- Cualquier cambio en la estrategia o estructura

**📋 CHECKLIST DE ACTUALIZACIÓN** (completar al final de cada fase):
- [ ] Actualizar "Estado actual" con la fase completada
- [ ] Actualizar "Próximo paso" con la siguiente tarea
- [ ] Actualizar "Última actualización" con fecha actual
- [ ] Actualizar sección de "Apps Existentes y su Estado"
- [ ] Actualizar sección de progreso de fases
- [ ] Agregar detalles específicos de la fase completada

---

**Última actualización**: 2025-01-27  
**Estado actual**: FASE 1.4 completada - Apps Content, Competitions, Teams y Rosters creadas exitosamente  
**Próximo paso**: FASE 2.1 - Crear backup completo de la base de datos