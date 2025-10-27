"""
Utilidades para el sistema de gestión de imágenes y videos.
Migradas desde videos.utils para la nueva app content.
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

        # Crear objeto imagen
        image = vision.Image(content=content)

        # Detectar contenido inapropiado
        safe_search_response = client.safe_search_detection(image=image)
        safe_search = safe_search_response.safe_search_annotation

        # Evaluar seguridad
        safe = True
        reasons = []

        # Verificar cada categoría de seguridad
        if safe_search.adult in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
            safe = False
            reasons.append('Contenido adulto detectado')

        if safe_search.medical in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
            safe = False
            reasons.append('Contenido médico detectado')

        if safe_search.spoof in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
            safe = False
            reasons.append('Contenido falso detectado')

        if safe_search.violence in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
            safe = False
            reasons.append('Contenido violento detectado')

        if safe_search.racy in [vision.Likelihood.LIKELY, vision.Likelihood.VERY_LIKELY]:
            safe = False
            reasons.append('Contenido sugerente detectado')

        # Extraer etiquetas si se solicita
        labels = []
        if extract_labels:
            label_response = client.label_detection(image=image)
            labels = [label.description for label in label_response.label_annotations]

        # Extraer texto si se solicita
        text = ''
        if extract_text:
            text_response = client.text_detection(image=image)
            if text_response.text_annotations:
                text = text_response.text_annotations[0].description

        return {
            'safe': safe,
            'reasons': reasons,
            'labels': labels,
            'text': text,
            'details': {
                'api_response_ok': True,
                'adult': safe_search.adult.name,
                'medical': safe_search.medical.name,
                'spoof': safe_search.spoof.name,
                'violence': safe_search.violence.name,
                'racy': safe_search.racy.name,
                'labels_count': len(labels),
                'text_length': len(text)
            }
        }

    except Exception as e:
        return {
            'safe': False,
            'reasons': [f'Error en Vision API: {str(e)}'],
            'labels': [],
            'text': '',
            'details': {
                'api_response_ok': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
        }


def process_vision_tags_for_volleyball(labels, text):
    """
    Procesa las etiquetas y texto de Google Vision API para extraer información relevante para voleibol

    Args:
        labels: Lista de etiquetas de Vision API
        text: Texto extraído de la imagen

    Returns:
        list: Lista de etiquetas procesadas y filtradas para voleibol
    """
    # Palabras clave relacionadas con voleibol
    volleyball_keywords = [
        'volleyball', 'voleibol', 'voley', 'sport', 'deporte', 'athlete', 'atleta',
        'team', 'equipo', 'match', 'partido', 'game', 'juego', 'player', 'jugador',
        'ball', 'pelota', 'net', 'red', 'court', 'pista', 'gymnasium', 'gimnasio',
        'uniform', 'uniforme', 'jersey', 'camiseta', 'shorts', 'pantalones',
        'celebration', 'celebración', 'victory', 'victoria', 'win', 'ganar',
        'training', 'entrenamiento', 'practice', 'práctica', 'coach', 'entrenador',
        'trophy', 'trofeo', 'medal', 'medalla', 'award', 'premio'
    ]

    # Palabras clave de categorías
    category_keywords = {
        'senior': ['senior', 'adulto', 'adult', 'mayor'],
        'juvenil': ['juvenil', 'youth', 'joven', 'young'],
        'cadete': ['cadete', 'cadet', 'teenager', 'adolescente'],
        'infantil': ['infantil', 'child', 'niño', 'kid', 'young'],
        'alevin': ['alevín', 'alevin', 'little', 'pequeño'],
        'benjamin': ['benjamín', 'benjamin', 'small', 'muy pequeño']
    }

    # Palabras clave de tipos de imagen
    image_type_keywords = {
        'match': ['match', 'partido', 'game', 'juego', 'competition', 'competición'],
        'celebration': ['celebration', 'celebración', 'victory', 'victoria', 'win', 'ganar'],
        'training': ['training', 'entrenamiento', 'practice', 'práctica', 'workout'],
        'team_photo': ['team', 'equipo', 'group', 'grupo', 'photo', 'foto'],
        'facilities': ['court', 'pista', 'gymnasium', 'gimnasio', 'facility', 'instalación']
    }

    processed_tags = []

    # Procesar etiquetas de Vision API
    for label in labels:
        label_lower = label.lower()
        
        # Verificar si es relevante para voleibol
        if any(keyword in label_lower for keyword in volleyball_keywords):
            processed_tags.append(label_lower)

    # Procesar texto extraído
    if text:
        text_lower = text.lower()
        
        # Buscar categorías
        for category, keywords in category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                processed_tags.append(category)

        # Buscar tipos de imagen
        for image_type, keywords in image_type_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                processed_tags.append(image_type)

    # Limpiar y normalizar etiquetas
    cleaned_tags = []
    for tag in processed_tags:
        # Normalizar texto
        tag = unicodedata.normalize('NFD', tag)
        tag = ''.join(c for c in tag if unicodedata.category(c) != 'Mn')
        tag = re.sub(r'[^\w\s]', '', tag)
        tag = tag.strip()
        
        if tag and len(tag) > 2 and tag not in cleaned_tags:
            cleaned_tags.append(tag)

    return cleaned_tags[:10]  # Limitar a 10 etiquetas


def process_uploaded_image(uploaded_file, optimize_for_mobile=False):
    """
    Procesa una imagen subida, convirtiendo HEIC a JPEG si es necesario
    
    Args:
        uploaded_file: Archivo subido por el usuario
        optimize_for_mobile: Si optimizar para dispositivos móviles
        
    Returns:
        tuple: (archivo_procesado, extension_original, fue_convertido)
    """
    from PIL import Image as PILImage
    from io import BytesIO
    import os
    
    # Obtener información del archivo
    original_name = uploaded_file.name
    original_ext = os.path.splitext(original_name)[1].lower()
    
    # Leer el archivo
    uploaded_file.seek(0)
    file_content = uploaded_file.read()
    uploaded_file.seek(0)
    
    was_converted = False
    
    try:
        # Abrir imagen con PIL
        image = PILImage.open(BytesIO(file_content))
        
        # Convertir a RGB si es necesario (para JPEG)
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        # Optimizar para móvil si se solicita
        if optimize_for_mobile:
            # Redimensionar si es muy grande
            max_size = (1920, 1920)
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, PILImage.Resampling.LANCZOS)
        
        # Si es HEIC/HEIF, convertir a JPEG
        if original_ext in ['.heic', '.heif']:
            was_converted = True
            output_format = 'JPEG'
            output_ext = '.jpg'
        else:
            output_format = image.format or 'JPEG'
            output_ext = original_ext
        
        # Guardar en BytesIO
        output = BytesIO()
        image.save(output, format=output_format, quality=85, optimize=True)
        output.seek(0)
        
        # Crear archivo Django
        from django.core.files.base import ContentFile
        processed_file = ContentFile(
            output.getvalue(),
            name=os.path.splitext(original_name)[0] + output_ext
        )
        
        return processed_file, original_ext, was_converted
        
    except Exception as e:
        # Si hay error, devolver el archivo original
        uploaded_file.seek(0)
        return uploaded_file, original_ext, False


def normalize_text(text):
    """
    Normaliza texto para búsquedas, eliminando acentos y caracteres especiales
    
    Args:
        text: Texto a normalizar
        
    Returns:
        str: Texto normalizado
    """
    if not text:
        return ''
    
    # Normalizar unicode
    text = unicodedata.normalize('NFD', text)
    
    # Eliminar acentos
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    
    # Convertir a minúsculas
    text = text.lower()
    
    # Eliminar caracteres especiales excepto espacios
    text = re.sub(r'[^\w\s]', '', text)
    
    return text.strip()


def extract_youtube_id(url):
    """
    Extrae el ID de un video de YouTube desde una URL
    
    Args:
        url: URL de YouTube
        
    Returns:
        str: ID del video o None si no es válido
    """
    if not url:
        return None
    
    # Patrones comunes de YouTube
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/user\/[^\/]+\/.*#p\/[a-z]\/[0-9]+\/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def generate_thumbnail_url(youtube_id, quality='medium'):
    """
    Genera URL de thumbnail de YouTube
    
    Args:
        youtube_id: ID del video de YouTube
        quality: Calidad del thumbnail ('default', 'medium', 'high', 'standard', 'maxres')
        
    Returns:
        str: URL del thumbnail
    """
    if not youtube_id:
        return None
    
    quality_map = {
        'default': 'default',
        'medium': 'mqdefault',
        'high': 'hqdefault',
        'standard': 'sddefault',
        'maxres': 'maxresdefault'
    }
    
    quality_code = quality_map.get(quality, 'mqdefault')
    return f'https://img.youtube.com/vi/{youtube_id}/{quality_code}.jpg'