"""
Utilidades para el sistema de gestión de imágenes y videos
"""
import html
import unicodedata
import re
from django.conf import settings


def check_image_with_vision_api(image_file, extract_labels=True, extract_text=True):
    """
    Verifica una imagen usando Google Vision API para detectar contenido inapropiado y extraer etiquetas

    Args:
        image_file: El archivo de imagen a verificar
        extract_labels: Si extraer etiquetas de la imagen
        extract_text: Si extraer texto de la imagen

    Returns:
        dict: Resultado de la verificación con los campos:
            - safe (bool): Si la imagen es segura
            - reasons (list): Lista de razones si no es segura
            - labels (list): Etiquetas detectadas
            - text (str): Texto detectado
            - details (dict): Detalles completos de la API
    """

    if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
        return {
            'safe': True,
            'reasons': [],
            'labels': [],
            'text': '',
            'details': {'message': 'Google Vision API no está habilitada'}
        }

    try:
        from google.cloud import vision

        # Inicializar cliente
        client = vision.ImageAnnotatorClient()

        # Leer imagen
        if hasattr(image_file, 'read'):
            content = image_file.read()
            image_file.seek(0)  # Reset file pointer
        else:
            with open(image_file.path, 'rb') as f:
                content = f.read()

        image = vision.Image(content=content)

        # Detectar contenido explícito/violento
        response = client.safe_search_detection(image=image)
        safe_search = response.safe_search_annotation

        # Definir niveles de seguridad
        likelihood_levels = {
            vision.Likelihood.UNKNOWN: 0,
            vision.Likelihood.VERY_UNLIKELY: 1,
            vision.Likelihood.UNLIKELY: 2,
            vision.Likelihood.POSSIBLE: 3,
            vision.Likelihood.LIKELY: 4,
            vision.Likelihood.VERY_LIKELY: 5
        }

        # Verificar diferentes tipos de contenido
        checks = {
            'adult': safe_search.adult,
            'violence': safe_search.violence,
            'racy': safe_search.racy,
            'medical': safe_search.medical,
            'spoof': safe_search.spoof
        }

        # Determinar si es segura (umbral: POSSIBLE o mayor es inseguro)
        unsafe_reasons = []
        for content_type, likelihood in checks.items():
            level = likelihood_levels.get(likelihood, 0)
            if level >= 3:  # POSSIBLE o mayor
                unsafe_reasons.append(f'{content_type}: {likelihood.name}')

        is_safe = len(unsafe_reasons) == 0

        # Inicializar variables para etiquetas y texto
        detected_labels = []
        detected_text = ""

        # Detectar etiquetas/objetos (opcional)
        if extract_labels:
            try:
                label_detection = client.label_detection(image=image)
                labels = label_detection.label_annotations

                # Extraer etiquetas relevantes para voleibol
                volleyball_related = ['volleyball', 'sport', 'game', 'team', 'player', 'ball', 'court', 'athletic',
                                      'competition']
                general_labels = ['celebration', 'victory', 'team', 'group', 'people', 'indoor', 'outdoor']

                for label in labels:
                    if label.score > 0.5:  # Solo etiquetas con alta confianza
                        label_text = label.description.lower()
                        # Incluir etiquetas relacionadas con voleibol o generales útiles
                        if (any(keyword in label_text for keyword in volleyball_related) or
                                any(keyword in label_text for keyword in general_labels) or
                                label.score > 0.8):  # O etiquetas con muy alta confianza
                            detected_labels.append(label_text)

                # Limitar a las 10 etiquetas más relevantes
                detected_labels = detected_labels[:10]

            except Exception as e:
                print(f"Error en detección de etiquetas: {e}")

        # Detectar texto (opcional)
        if extract_text:
            try:
                text_detection = client.text_detection(image=image)
                if text_detection.text_annotations:
                    detected_text = text_detection.text_annotations[0].description
                    # Limpiar y limitar texto detectado
                    detected_text = detected_text[:500] if detected_text else ""
            except Exception as e:
                print(f"Error en detección de texto: {e}")

        return {
            'safe': is_safe,
            'reasons': unsafe_reasons,
            'labels': detected_labels,
            'text': detected_text,
            'details': {
                'safe_search': {
                    'adult': safe_search.adult.name,
                    'violence': safe_search.violence.name,
                    'racy': safe_search.racy.name,
                    'medical': safe_search.medical.name,
                    'spoof': safe_search.spoof.name
                },
                'detected_text': detected_text,
                'detected_labels': detected_labels,
                'api_response_ok': True
            }
        }

    except Exception as e:
        # Log del error pero continuar
        print(f"Error en Google Vision API: {e}")

        return {
            'safe': False,  # Default a NO seguro si hay error - requiere moderación manual
            'reasons': ['Google Vision API error - requires manual review'],
            'labels': [],
            'text': '',
            'details': {
                'error': str(e),
                'api_response_ok': False
            }
        }


def process_vision_tags_for_volleyball(detected_labels, detected_text=''):
    """
    Procesa las etiquetas detectadas por Vision API para contexto de voleibol

    Args:
        detected_labels: Lista de etiquetas detectadas por Vision API
        detected_text: Texto detectado en la imagen

    Returns:
        list: Lista de etiquetas procesadas y relevantes para voleibol
    """
    # Mapeo de etiquetas en inglés a español
    label_mapping = {
        'volleyball': 'voleibol',
        'sport': 'deporte',
        'game': 'juego',
        'team': 'equipo',
        'player': 'jugador',
        'ball': 'balón',
        'court': 'cancha',
        'athletic': 'atlético',
        'competition': 'competición',
        'celebration': 'celebración',
        'victory': 'victoria',
        'group': 'grupo',
        'people': 'personas',
        'indoor': 'interior',
        'outdoor': 'exterior',
        'uniform': 'uniforme',
        'net': 'red',
        'spike': 'remate',
        'serve': 'saque',
        'jump': 'salto',
        'stadium': 'estadio',
        'gymnasium': 'gimnasio',
        'tournament': 'torneo',
        'match': 'partido',
        'win': 'victoria',
        'loss': 'derrota'
    }

    processed_tags = []

    # Procesar etiquetas detectadas
    for label in detected_labels:
        # Convertir a español si tiene mapeo
        spanish_label = label_mapping.get(label.lower(), label.lower())
        processed_tags.append(spanish_label)

    # Buscar palabras clave en texto detectado
    if detected_text:
        text_lower = detected_text.lower()
        volleyball_keywords = ['voleibol', 'volleyball', 'set', 'punto', 'partido', 'equipo', 'victoria', 'derrota']

        for keyword in volleyball_keywords:
            if keyword in text_lower and keyword not in processed_tags:
                processed_tags.append(keyword)

    # Eliminar duplicados manteniendo orden
    seen = set()
    unique_tags = []
    for tag in processed_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags[:8]  # Limitar a 8 etiquetas automáticas


def get_image_metadata(image_file):
    """
    Extrae metadatos básicos de una imagen usando PIL

    Args:
        image_file: El archivo de imagen

    Returns:
        dict: Metadatos de la imagen
    """
    try:
        from PIL import Image

        if hasattr(image_file, 'file'):
            img = Image.open(image_file.file)
        else:
            img = Image.open(image_file.path)

        # Obtener información básica
        metadata = {
            'format': img.format,
            'mode': img.mode,
            'size': img.size,
            'width': img.width,
            'height': img.height,
        }

        # EXIF data (si está disponible)
        if hasattr(img, '_getexif') and img._getexif():
            exif = img._getexif() or {}
            metadata['exif'] = {
                'datetime': exif.get(306),  # DateTime
                'make': exif.get(271),  # Make
                'model': exif.get(272),  # Model
                'orientation': exif.get(274),  # Orientation
            }

        return metadata

    except Exception as e:
        print(f"Error extrayendo metadatos: {e}")
        return {}


def generate_thumbnail(image_file, size=(300, 300)):
    """
    Genera una miniatura de la imagen

    Args:
        image_file: El archivo de imagen
        size: Tupla con el tamaño deseado (width, height)

    Returns:
        PIL.Image: La imagen miniatura
    """
    try:
        from PIL import Image

        if hasattr(image_file, 'file'):
            img = Image.open(image_file.file)
        else:
            img = Image.open(image_file.path)

        # Crear miniatura manteniendo proporciones
        img.thumbnail(size, Image.Resampling.LANCZOS)

        return img

    except Exception as e:
        print(f"Error generando miniatura: {e}")
        return None


def optimize_image_for_web(image_file, max_width=1920, quality=85):
    """
    Optimiza una imagen para uso web reduciendo tamaño y calidad

    Args:
        image_file: El archivo de imagen
        max_width: Ancho máximo en píxeles
        quality: Calidad JPEG (1-100)

    Returns:
        BytesIO: La imagen optimizada como bytes
    """
    try:
        from PIL import Image
        from io import BytesIO

        if hasattr(image_file, 'file'):
            img = Image.open(image_file.file)
        else:
            img = Image.open(image_file.path)

        # Convertir a RGB si es necesario (para JPEG)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Redimensionar si es necesario
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        # Guardar con calidad reducida
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)

        return output

    except Exception as e:
        print(f"Error optimizando imagen: {e}")
        return None


def convert_heic_to_jpeg(heic_file, max_size=2048, quality=85):
    """
    Convierte una imagen HEIC a JPEG de forma optimizada para móvil delegando en sanitize_image.

    Args:
        heic_file: Archivo HEIC (UploadedFile o path)
        max_size: Tamaño máximo de la imagen (por defecto 2048px)
        quality: Calidad JPEG (por defecto 85)

    Returns:
        BytesIO: Imagen convertida a JPEG
    """
    sanitized = sanitize_image(heic_file, max_size=max_size, quality=quality)
    sanitized.seek(0)
    return sanitized.file


def extract_frame_from_live_photo(video_file):
    """
    Extrae el frame principal de un video de Live Photo

    Args:
        video_file: Archivo de video MOV/MP4

    Returns:
        BytesIO: Frame extraído como JPEG
    """
    try:
        from PIL import Image
        from io import BytesIO
        import tempfile
        import os

        # Guardar temporalmente el video
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mov') as tmp:
            if hasattr(video_file, 'read'):
                tmp.write(video_file.read())
            else:
                with open(video_file, 'rb') as f:
                    tmp.write(f.read())
            tmp_path = tmp.name

        try:
            # Usar ffmpeg o moviepy para extraer frame
            # Por ahora, retornar None para indicar que no se pudo procesar
            # TODO: Implementar con opencv-python o moviepy si se necesita
            return None
        finally:
            # Limpiar archivo temporal
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        print(f"Error extrayendo frame de Live Photo: {str(e)}")
        return None


def sanitize_image(image_file, max_size=2560, quality=85):
    """
    Sanea una imagen eliminando metadatos EXIF/GPS, normalizando la orientación
    y redimensionando si excede el tamaño máximo.

    Args:
        image_file: Django UploadedFile, File, BytesIO, o path
        max_size: Tamaño máximo de la imagen (por defecto 2560px)
        quality: Calidad JPEG (por defecto 85)

    Returns:
        InMemoryUploadedFile: Imagen saneada en memoria con identificador UUID y sin EXIF
    """
    try:
        from PIL import Image, ImageOps
        from io import BytesIO
        import uuid
        from django.core.files.uploadedfile import InMemoryUploadedFile

        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass

        # Abrir imagen
        if hasattr(image_file, 'file'):
            img = Image.open(image_file.file)
        elif hasattr(image_file, 'read'):
            img = Image.open(image_file)
        else:
            img = Image.open(image_file)

        # Corregir orientación física según EXIF antes de purgar metadatos
        img = ImageOps.exif_transpose(img) or img

        # Redimensionar si supera límites razonables
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Convertir a RGB (manejando transparencia con fondo blanco)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            else:
                rgba = img.convert('RGBA')
                background.paste(rgba, mask=rgba.split()[-1])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Guardar como JPEG en memoria sin ningún parámetro de metadatos EXIF
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
        output.seek(0)

        # Generar nombre UUID no predecible
        uuid_filename = f"{uuid.uuid4().hex}.jpg"
        field_name = getattr(image_file, 'field_name', None)

        return InMemoryUploadedFile(
            output,
            field_name=field_name,
            name=uuid_filename,
            content_type='image/jpeg',
            size=output.getbuffer().nbytes,
            charset=None,
        )

    except Exception as e:
        raise RuntimeError(f"Error saneando imagen: {str(e)}") from e


def build_uuid_upload_path(base_dir, filename):
    """
    Construye una ruta con prefijo base_dir y nombre de archivo UUID no predecible.
    Reutiliza el UUID si ya es válido, y normaliza extensiones HEIC/HEIF a .jpg.
    """
    import os
    import uuid

    name, ext = os.path.splitext(filename)
    ext = ext.lower()
    if not ext or ext in ['.heic', '.heif']:
        ext = '.jpg'
    try:
        uuid_hex = uuid.UUID(name).hex
    except (ValueError, AttributeError):
        uuid_hex = uuid.uuid4().hex
    return f"{base_dir.rstrip('/')}/{uuid_hex}{ext}"


def sanitize_model_image_field(instance, field_name, max_size=2560):
    """
    Sanea un campo de imagen de un modelo Django si se le ha asignado un nuevo archivo
    no guardado en almacenamiento (_committed=False).
    """
    field = getattr(instance, field_name, None)
    if field and not getattr(field, '_committed', True):
        sanitized = sanitize_image(field, max_size=max_size)
        setattr(instance, field_name, sanitized)
        return sanitized
    return None


def process_uploaded_image(uploaded_file, optimize_for_mobile=True):
    """
    Procesa una imagen subida mediante el pipeline centralizado de saneamiento:
    elimina metadatos EXIF/GPS, normaliza orientación y formato, y asigna identificador UUID.

    Args:
        uploaded_file: Django UploadedFile
        optimize_for_mobile: Si optimizar la imagen para dispositivos móviles

    Returns:
        tuple: (processed_file, original_extension, was_converted)
    """
    import os

    original_name = uploaded_file.name
    original_ext = os.path.splitext(original_name)[1].lower()

    max_size = 2048 if optimize_for_mobile else 2560
    quality = 85 if optimize_for_mobile else 90

    sanitized_file = sanitize_image(uploaded_file, max_size=max_size, quality=quality)
    was_converted = original_ext not in ['.jpg', '.jpeg']

    return sanitized_file, original_ext, was_converted


def is_live_photo_video(filename):
    """
    Detecta si un archivo es el componente de video de una Live Photo

    Live Photos de iPhone tienen nombres como:
    - IMG_1234.HEIC (foto)
    - IMG_1234.MOV (video)

    Args:
        filename: Nombre del archivo

    Returns:
        bool: True si parece ser un video de Live Photo
    """
    import os
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Videos de Live Photo suelen ser MOV o MP4
    if ext not in ['.mov', '.mp4']:
        return False

    # Suelen tener nombres como IMG_XXXX o similar
    # Esta es una detección heurística, puede mejorarse
    return name.upper().startswith('IMG_') or name.upper().startswith('DSC_')

def normalize_team_name(name):
    """
    Normaliza un nombre de equipo para comparación, manejando entidades HTML
    y caracteres especiales del catalán y español.
    
    Args:
        name (str): Nombre del equipo a normalizar
        
    Returns:
        str: Nombre normalizado para comparación
    """
    if not name:
        return ''
    
    # Convertir entidades HTML comunes a caracteres reales
    # Manejar casos específicos como #39; -> ', &apos; -> ', etc.
    normalized = name
    
    # Reemplazar entidades HTML comunes manualmente antes de html.unescape
    html_entities = {
        '#39;': "'",
        '&apos;': "'",
        '&quot;': '"',
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&nbsp;': ' ',
    }
    
    for entity, char in html_entities.items():
        normalized = normalized.replace(entity, char)
    
    # Luego usar html.unescape para el resto
    normalized = html.unescape(normalized)
    
    # Quitar acentos y diacríticos
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    
    # Convertir a mayúsculas y limpiar espacios
    normalized = normalized.upper().strip()
    
    # Quitar caracteres especiales pero mantener apóstrofes, guiones y espacios
    # Esto preserva caracteres importantes del catalán como la ç, ñ, etc.
    normalized = re.sub(r'[^\w\s\'-]', ' ', normalized)
    normalized = ' '.join(normalized.split())
    
    return normalized


def find_duplicate_team_by_name(team_name, category=None, exclude_id=None):
    """
    Busca equipos duplicados por nombre normalizado.
    
    Args:
        team_name (str): Nombre del equipo a buscar
        category: Categoría a filtrar (opcional)
        exclude_id: ID del equipo a excluir de la búsqueda (opcional)
        
    Returns:
        Team: Equipo duplicado encontrado o None
    """
    from .models import Team
    
    normalized_name = normalize_team_name(team_name)
    
    # Buscar equipos con el mismo nombre normalizado
    teams = Team.objects.all()
    if category:
        teams = teams.filter(category=category)
    if exclude_id:
        teams = teams.exclude(id=exclude_id)
    
    for team in teams:
        if normalize_team_name(team.name) == normalized_name:
            return team
    
    return None


def find_similar_team_by_name(team_name, category=None, threshold=0.85, exclude_id=None):
    """
    Busca equipos con nombres similares usando similitud de secuencia (Levenshtein).
    Útil para detectar cambios leves en nombres (ej: typos, cambio de patrocinador menor)
    
    Args:
        team_name (str): Nombre del equipo a buscar
        category: Categoría a filtrar (opcional)
        threshold (float): Umbral de similitud (0.0 a 1.0)
        exclude_id: ID del equipo a excluir de la búsqueda
        
    Returns:
        tuple: (Team, score) o (None, 0)
    """
    from .models import Team
    from difflib import SequenceMatcher
    
    normalized_target = normalize_team_name(team_name)
    best_match = None
    best_score = 0
    
    # Obtener candidatos (optimización: filtrar por longitud similar si hay muchos)
    teams = Team.objects.all()
    if category:
        teams = teams.filter(category=category)
    if exclude_id:
        teams = teams.exclude(id=exclude_id)
        
    for team in teams:
        normalized_current = normalize_team_name(team.name)
        
        # Calcular similitud
        ratio = SequenceMatcher(None, normalized_target, normalized_current).ratio()
        
        if ratio > best_score and ratio >= threshold:
            best_score = ratio
            best_match = team
            
    return best_match, best_score