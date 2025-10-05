"""
Utilidades para el sistema de gestión de imágenes
"""

from django.conf import settings


def check_image_with_vision_api(image_file):
    """
    Verifica una imagen usando Google Vision API para detectar contenido inapropiado
    
    Args:
        image_file: El archivo de imagen a verificar
        
    Returns:
        dict: Resultado de la verificación con los campos:
            - safe (bool): Si la imagen es segura
            - reasons (list): Lista de razones si no es segura
            - details (dict): Detalles completos de la API
    """
    
    if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
        return {
            'safe': True,
            'reasons': [],
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
        
        # Detectar texto (opcional)
        text_detection = client.text_detection(image=image)
        detected_text = text_detection.text_annotations[0].description if text_detection.text_annotations else ""
        
        return {
            'safe': is_safe,
            'reasons': unsafe_reasons,
            'details': {
                'safe_search': {
                    'adult': safe_search.adult.name,
                    'violence': safe_search.violence.name,
                    'racy': safe_search.racy.name,
                    'medical': safe_search.medical.name,
                    'spoof': safe_search.spoof.name
                },
                'detected_text': detected_text[:500] if detected_text else "",
                'api_response_ok': True
            }
        }
        
    except Exception as e:
        # Log del error pero continuar
        print(f"Error en Google Vision API: {e}")
        
        return {
            'safe': True,  # Default a seguro si hay error
            'reasons': [],
            'details': {
                'error': str(e),
                'api_response_ok': False
            }
        }


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
                'make': exif.get(271),      # Make
                'model': exif.get(272),     # Model
                'orientation': exif.get(274), # Orientation
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