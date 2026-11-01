# Sistema de Gestión de Imágenes - I Love Voley

## Descripción General

El sistema de gestión de imágenes permite a los usuarios subir, moderar y visualizar imágenes relacionadas con partidos de voleibol. Incluye funcionalidades de moderación manual y automática mediante Google Vision API.

## Características Principales

### 🖼️ **Galería de Imágenes**
- Vista responsive con grid adaptable
- Filtros avanzados por búsqueda, etiquetas, tipo, categoría, año y estado
- Filtro especial para imágenes con/sin partido vinculado
- Paginación eficiente
- Lightbox para visualización expandida
- Integración opcional con partidos y categorías
- Sugerencias de etiquetas populares

### 📤 **Subida de Imágenes**
- Formulario con drag & drop funcional
- Soporte para desktop y móvil
- Vista previa antes de subir
- Validación automática de formato y tamaño
- Vinculación opcional a partidos
- Sistema de tipos de imagen (partido, celebración, entrenamiento, etc.)
- Etiquetas manuales y automáticas
- Auto-detección de etiquetas con Vision API

### 🛡️ **Sistema de Moderación**
- Moderación manual por administradores
- Moderación automática con Google Vision API
- Estados: pendiente, aprobada, rechazada
- Acciones masivas desde el admin
- Notas de moderación
- Auto-etiquetado durante moderación

### 🔗 **Integración Completa**
- Enlaces en navegación principal
- Galería integrada en detalle de partidos
- Auto-asignación inteligente de categoría y año
- Sistema de URLs RESTful
- Imágenes independientes para eventos del club
- Búsqueda unificada por etiquetas

## Configuración

### Dependencias

Las siguientes dependencias están incluidas en `pyproject.toml`:

```
google-cloud-vision==3.16.0  # Para moderación automática (opcional)
django-storages==1.14.6      # Para almacenamiento avanzado (opcional)
Pillow==13.0.0               # Para procesamiento de imágenes (incluido)
pillow-heif==1.8.1           # Lectura y conversión de HEIC/HEIF (iPhone)
```

### Variables de Entorno

Agrega estas variables a tu archivo `.env`:

```bash
# Google Vision API (opcional)
GOOGLE_VISION_ENABLED=false
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json

# Moderación automática (opcional; por defecto toma el valor de DEBUG)
AUTO_MODERATION_ENABLED=false

# Ventana de agrupación de avisos de la cola de subida (segundos, #611)
UPLOAD_BATCH_DEBOUNCE_SECONDS=15
```

### Configuración de Almacenamiento

Por defecto, las imágenes se almacenan en el sistema de archivos local:

```python
# En settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Configuración de subida
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024  # 60MB (subidas en lote)
```

#### Para servidor privado con `django-storages`:

```python
# Ejemplo para almacenamiento personalizado
DEFAULT_FILE_STORAGE = 'storages.backends.ftp.FTPStorage'
FTP_STORAGE_LOCATION = 'ftp://user:pass@host:port/path'
```

## Google Vision API

### Configuración

1. **Crear proyecto en Google Cloud Console**
2. **Habilitar Vision API**
3. **Crear service account y descargar JSON key**
4. **Configurar variables de entorno**:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
export GOOGLE_VISION_ENABLED=true
export AUTO_MODERATION_ENABLED=true  # Para auto-aprobación
```

### Funcionalidades

- **Detección de contenido inapropiado**: adult, violence, racy content
- **Detección de texto**: extrae texto de imágenes
- **Detección de objetos**: extrae etiquetas automáticas relevantes
- **Auto-moderación**: aprueba automáticamente imágenes seguras
- **Auto-etiquetado**: procesa etiquetas en español para voleibol
- **Logging detallado**: guarda resultados para auditoría
- **Asíncrono**: el análisis corre en la tarea Celery `analyze_image_with_vision` tras guardar la imagen; la auto-aprobación solo actúa si la imagen sigue `pending` (no pisa una decisión humana)

> La lectura de actas fotografiadas usa **Gemini**, no Vision API, y es independiente de la galería: se activa con `ACTA_VISION_ENABLED` y `GEMINI_API_KEY` (modelo en `GEMINI_ACTA_MODEL`).

### Tipos de Verificación

| Tipo | Descripción |
|------|-------------|
| `adult` | Contenido para adultos |
| `violence` | Contenido violento |
| `racy` | Contenido sugestivo |
| `medical` | Contenido médico |
| `spoof` | Contenido falsificado |

### Niveles de Confianza

- `VERY_UNLIKELY` (1)
- `UNLIKELY` (2) 
- `POSSIBLE` (3) ⚠️ **Umbral de rechazo**
- `LIKELY` (4)
- `VERY_LIKELY` (5)

## Tipos de Imagen y Etiquetas

### Tipos de Imagen Disponibles

- **Partido**: Imágenes relacionadas con partidos específicos
- **Celebración**: Celebraciones, victorias, eventos especiales
- **Entrenamiento**: Sesiones de entrenamiento y práctica
- **Foto de Equipo**: Fotos oficiales y grupales del equipo
- **Instalaciones**: Imágenes de las instalaciones del club
- **Otro**: Cualquier otra imagen relacionada con el club

### Sistema de Etiquetas

#### Etiquetas Manuales
- Los usuarios pueden agregar etiquetas separadas por comas
- Máximo 10 etiquetas por imagen
- Cada etiqueta puede tener hasta 30 caracteres
- Se normalizan automáticamente (minúsculas, sin espacios extra)

#### Etiquetas Automáticas
- Detectadas por Google Vision API
- Traducidas automáticamente al español
- Filtradas por relevancia para voleibol
- Incluyen: voleibol, deporte, equipo, jugador, celebración, etc.
- Se combinan con etiquetas manuales para búsqueda

## Uso del Sistema

### Para Usuarios

1. **Subir Imagen**:
   - Acceder a `/content/imagenes/subir/` (las rutas antiguas `/videos/...` redirigen con 301)
   - Arrastrar imagen o hacer clic para seleccionar
   - Completar título y seleccionar tipo de imagen
   - Agregar etiquetas manuales (opcional)
   - Vincular a partido específico (opcional)
   - La imagen queda pendiente de moderación
   - Se procesan etiquetas automáticas si Vision API está habilitada

2. **Ver Galería**:
   - Acceder a `/content/imagenes/`
   - Usar filtros avanzados:
     - Búsqueda general en título, descripción y etiquetas
     - Filtro específico por etiquetas
     - Filtro por tipo de imagen
     - Filtro por imágenes con/sin partido
     - Filtro por categoría y año
   - Ver etiquetas populares sugeridas
   - Hacer clic en imagen para vista expandida

3. **Cola de subida tolerante a mala cobertura** (#611, #636):
   - Las fotos se encolan en el navegador (IndexedDB `ilovevoley_upload_queue`), se comprimen a máx. 2560 px en JPEG 0.85 y se suben una a una a `/content/api/imagenes/subir/` (`static/js/upload_queue.js`)
   - Reintentos con backoff exponencial y Background Sync del service worker (`sync-photo-uploads`); widget flotante global en `base.html` con «Quitar» por foto y «Vaciar cola»
   - El endpoint es idempotente por `client_upload_id` (clave en Redis, 24 h): un corte de red tras guardar no duplica la foto
   - Los avisos se agrupan por `batch_id`: la tarea `content.flush_upload_batch_notifications` envía un único email de moderación y un único push de álbum por lote (ventana `UPLOAD_BATCH_DEBOUNCE_SECONDS`)
   - En iOS el blob se copia a memoria antes del POST (Safari mandaba multipart vacío con el SW activo); un blob ilegible pasa a error sin reintentar

4. **Compartir desde la galería del móvil** (share target de la PWA, #524):
   - El manifiesto declara `share_target` hacia `/content/imagenes/compartida/`; solo usuarios con membresía aprobada en el club
   - Cada fichero se valida abriéndolo con Pillow (#599): JPG, PNG, WebP o HEIC de hasta 10 MB, máximo 20 por envío
   - Se guardan en `SharedUpload` (filas efímeras de 24 h) y se redirige a la subida simple o múltiple con `?share=`

5. **Solicitar la retirada de una foto** (#362):
   - Desde el detalle de una imagen aprobada, el deportista etiquetado o su familia (`Person.user` o `User.children`) envía la solicitud con motivo opcional (`ImageRemovalRequest`)
   - Solo una solicitud pendiente por imagen; la resuelve un moderador en `/core/moderacion/` (eliminar la foto o descartar) y el registro se conserva aunque la imagen se borre
   - La página `/core/transparencia-imagen/` (#222) explica en claro quién ve las fotos

### Para Administradores

1. **Moderar Imágenes**:
   ```bash
   # Acceder al admin de Django
   /admin/content/image/   # en producción el prefijo es DJANGO_ADMIN_URL
   
   # O usar URLs específicas
   /content/admin/imagenes/moderar/
   ```

2. **Acciones Disponibles**:
   - Aprobar/rechazar individualmente
   - Acciones masivas
   - Verificar con Vision API
   - Editar notas de moderación

3. **Verificación Manual con Vision API**:
   ```python
   # En Django shell
   from ilovevoley.videos.utils import check_image_with_vision_api
   from ilovevoley.content.models import Image
   
   image = Image.objects.get(id=1)
   result = check_image_with_vision_api(image.image)
   print(result)
   ```

## API y URLs

### URLs Principales

```python
# Galería (app content)
/content/imagenes/                     # Galería de imágenes (agrupada por álbumes)
/content/imagenes/individual/          # Galería de imágenes individuales
/content/imagenes/subir/               # Formulario de subida drag & drop
/content/imagenes/subir-multiples/     # Subida múltiple
/content/api/imagenes/subir/           # Endpoint unitario idempotente de la cola de subida (#611)
/content/imagenes/compartida/          # Share target de la PWA (POST multipart)
/content/imagenes/favoritas/           # Imágenes favoritas del usuario
/content/imagenes/<id>/                # Detalle de imagen
/content/imagenes/<id>/etiquetar/      # Etiquetar deportistas
/content/imagenes/<id>/solicitar-retirada/  # Solicitud de retirada (deportista o familia)
/content/partidos/<id>/imagenes/       # Imágenes de un partido
/content/partidos/<id>/imagenes/zip/   # Descarga ZIP del álbum del partido
/content/imagenes/album/<uuid>/        # Imágenes de un álbum grupal
/core/transparencia-imagen/            # Página de transparencia: quién ve las fotos

# Moderación
/content/admin/imagenes/moderar/       # Panel de moderación de imágenes
/content/admin/imagenes/<id>/moderar/  # Moderar imagen específica
/content/admin/imagenes/moderar-masivo/ # Moderación en lote
/core/moderacion/                      # Panel de moderación global (usuarios, imágenes y solicitudes de retirada)
/core/api/image-removals/<id>/resolve/ # Resolver una solicitud de retirada
```

### Modelo de Datos (`ilovevoley.content.models.Image`)

```python
class Image(models.Model):
    # Archivo y metadatos
    image = models.ImageField(upload_to=image_upload_path)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Tipo y etiquetas
    image_type = models.CharField(max_length=20, choices=IMAGE_TYPES, default='other')
    tags = models.CharField(max_length=500, blank=True)  # Etiquetas manuales
    auto_tags = models.JSONField(default=list, blank=True)  # Etiquetas automáticas (Vision API)
    
    # Relaciones
    match = models.ForeignKey('competitions.Match', on_delete=models.CASCADE, null=True, blank=True)
    set_number = models.PositiveSmallIntegerField(null=True, blank=True)
    categories = models.ManyToManyField('core.Category', blank=True)
    persons = models.ManyToManyField('rosters.Person', blank=True)  # Deportistas etiquetados
    season = models.ForeignKey('core.Season', on_delete=models.PROTECT, null=True, blank=True)
    organization = models.ForeignKey('core.Organization', on_delete=models.PROTECT, null=True, blank=True)
    
    # Álbumes
    album_group_id = models.UUIDField(null=True, blank=True)
    album_name = models.CharField(max_length=200, blank=True)
    
    # Conversión HEIC
    original_format = models.CharField(max_length=10, blank=True)
    was_converted = models.BooleanField(default=False)
    
    # Miniaturas WebP/AVIF (400 y 1600 px)
    thumbnail_small / thumbnail_large / thumbnail_small_avif / thumbnail_large_avif
    
    # Usuario
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    upload_date = models.DateTimeField(auto_now_add=True)
    
    # Moderación
    status = models.CharField(choices=MODERATION_STATUS, default='pending')
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    moderation_date = models.DateTimeField(null=True, blank=True)
    moderation_notes = models.TextField(blank=True)
    
    # Google Vision API
    vision_api_checked = models.BooleanField(default=False)
    vision_api_safe = models.BooleanField(default=True)
    vision_api_details = models.JSONField(default=dict, blank=True)
```

## Comandos de Gestión

### Verificar Configuración

```bash
# Verificar que todo esté configurado correctamente
docker compose -f docker-compose.dev.yml run --rm web python manage.py check

# Crear migraciones si es necesario
docker compose -f docker-compose.dev.yml run --rm web python manage.py makemigrations

# Aplicar migraciones
docker compose -f docker-compose.dev.yml run --rm web python manage.py migrate
```

### Auto-etiquetado Masivo

```bash
# Auto-etiquetar todas las imágenes aprobadas pendientes
docker compose -f docker-compose.dev.yml run --rm web python manage.py autotag_images

# Procesar solo 10 imágenes con delay de 2 segundos
docker compose -f docker-compose.dev.yml run --rm web python manage.py autotag_images --limit 10 --delay 2.0

# Procesar todas las imágenes (incluso las ya verificadas)
docker compose -f docker-compose.dev.yml run --rm web python manage.py autotag_images --force --status all

# Simular procesamiento sin hacer cambios
docker compose -f docker-compose.dev.yml run --rm web python manage.py autotag_images --dry-run

# Ver ayuda completa
docker compose -f docker-compose.dev.yml run --rm web python manage.py autotag_images --help
```

### Renombrado de Ficheros

```bash
# Renombrar imágenes con nombres descriptivos y actualizar títulos genéricos
docker compose -f docker-compose.dev.yml run --rm web python manage.py rename_content_images --dry-run
```

### Moderación Masiva (Django Shell)

```python
# Aprobar todas las imágenes pendientes
from django.contrib.auth import get_user_model
from ilovevoley.content.models import Image

User = get_user_model()
admin_user = User.objects.filter(is_staff=True).first()
pending_images = Image.objects.filter(status='pending')

for image in pending_images:
    image.moderate(admin_user, approved=True, notes='Aprobación masiva')

print(f"Aprobadas {pending_images.count()} imágenes")
```

### Verificar con Vision API

```python
# Verificar imágenes pendientes con Vision API
from ilovevoley.content.models import Image
from ilovevoley.videos.utils import check_image_with_vision_api

for image in Image.objects.filter(vision_api_checked=False):
    try:
        result = check_image_with_vision_api(image.image)
        image.vision_api_checked = True
        image.vision_api_safe = result['safe']
        image.vision_api_details = result
        
        if not result['safe']:
            image.status = 'rejected'
            image.moderation_notes = f"Auto-rechazada: {', '.join(result['reasons'])}"
        
        image.save()
        print(f"Verificada imagen {image.id}: {'Segura' if result['safe'] else 'Insegura'}")
        
    except Exception as e:
        print(f"Error verificando imagen {image.id}: {e}")
```

## Validaciones y Restricciones

### Archivos
- **Formatos permitidos**: JPG, JPEG, PNG, WebP, HEIC/HEIF (se convierten a JPEG con `pillow-heif`)
- **Tamaño máximo**: 10MB
- **Validación**: Automática en formulario y modelo
- **Live Photo** (#594): `extract_frame_from_live_photo` (`ilovevoley/videos/utils.py`) extrae el fotograma con `ffmpeg` (instalado en la imagen Docker; sin él devuelve `None`). Hoy no está enganchado a las vistas de subida

### Permisos
- **Subida**: Usuarios autenticados y aprobados
- **Moderación**: admins y managers del club (tenant actual) y superusuarios
- **Visualización**: 
  - Usuarios normales: solo imágenes aprobadas
  - Administradores: todas las imágenes

### Organización de Archivos

```
media/
└── images/
    └── 2024/
        ├── 01/  # Enero
        ├── 02/  # Febrero
        └── ...
    └── 2025/
        └── ...
```

## Solución de Problemas

### Errores Comunes

1. **"Permission denied" al subir imagen**:
   ```bash
   # Verificar permisos del directorio media
   chmod 755 media/
   chown -R www-data:www-data media/
   ```

2. **Vision API no funciona**:
   ```bash
   # Verificar variables de entorno
   echo $GOOGLE_APPLICATION_CREDENTIALS
   echo $GOOGLE_VISION_ENABLED
   
   # Verificar service account
   cat $GOOGLE_APPLICATION_CREDENTIALS
   ```

3. **Imágenes no se muestran**:
   ```python
   # Verificar configuración MEDIA en settings.py
   MEDIA_URL = '/media/'
   MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
   
   # Verificar URLs en development
   if settings.DEBUG:
       urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
   ```

### Logs y Debugging

```python
# En views.py o utils.py, agregar logging
import logging
logger = logging.getLogger(__name__)

# Ejemplo en check_image_with_vision_api
logger.info(f"Verificando imagen {image_file.name} con Vision API")
logger.warning(f"Imagen marcada como insegura: {unsafe_reasons}")
```

## Personalización

### Cambiar Validaciones

```python
# En forms.py
def clean_image(self):
    image = self.cleaned_data.get('image')
    if image:
        # Cambiar tamaño máximo
        if image.size > 5 * 1024 * 1024:  # 5MB
            raise forms.ValidationError('Archivo demasiado grande')
        
        # Agregar más formatos
        allowed = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if not any(image.name.lower().endswith(ext) for ext in allowed):
            raise forms.ValidationError('Formato no válido')
    
    return image
```

### Cambiar Umbral de Vision API

```python
# En ilovevoley/videos/utils.py (hoy el umbral está fijo en 3 dentro de la función)
def check_image_with_vision_api(image_file, threshold=3):
    # Cambiar umbral de seguridad
    unsafe_reasons = []
    for content_type, likelihood in checks.items():
        level = likelihood_levels.get(likelihood, 0)
        if level >= threshold:  # Usar threshold personalizado
            unsafe_reasons.append(f'{content_type}: {likelihood.name}')
```

### Agregar Metadatos Adicionales

```python
# En models.py
class Image(models.Model):
    # ... campos existentes ...
    
    # Metadatos adicionales
    photographer = models.CharField(max_length=100, blank=True)
    camera_info = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    tags = models.CharField(max_length=500, blank=True)
```

## Seguridad

### Consideraciones
- Las imágenes se validan antes de almacenar
- Vision API proporciona capa adicional de seguridad
- Solo usuarios aprobados pueden subir contenido
- Moderación obligatoria antes de publicación
- Logs detallados para auditoría

### Recomendaciones
- Revisar regularmente imágenes reportadas
- Configurar alertas para contenido rechazado
- Backup regular de imágenes aprobadas
- Monitorear uso de almacenamiento
- Revisar configuración de Vision API periódicamente

---

## Soporte

Para problemas o dudas sobre el sistema de imágenes:

1. Revisar logs de Django: `docker compose -f docker-compose.dev.yml logs web`
2. Verificar configuración en `settings.py`
3. Comprobar variables de entorno en `.env`
4. Revisar documentación de Google Vision API
5. Verificar permisos de archivos y directorios