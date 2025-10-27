import os
import re
from PIL import Image as PILImage
from django.core.files.base import ContentFile
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def process_uploaded_image(image_file, convert_heic=True):
    """
    Procesa una imagen subida, convirtiendo HEIC a JPEG si es necesario
    
    Args:
        image_file: Archivo de imagen subido
        convert_heic: Si convertir HEIC a JPEG
    
    Returns:
        tuple: (archivo_procesado, formato_original, fue_convertido)
    """
    try:
        # Obtener información del archivo
        original_name = image_file.name
        original_format = os.path.splitext(original_name)[1].lower().lstrip('.')
        
        # Si es HEIC y queremos convertir
        if convert_heic and original_format in ['heic', 'heif']:
            try:
                # Convertir HEIC a JPEG
                image = PILImage.open(image_file)
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')
                
                # Crear nuevo archivo en memoria
                from io import BytesIO
                output = BytesIO()
                image.save(output, format='JPEG', quality=85)
                output.seek(0)
                
                # Crear nuevo archivo con extensión .jpg
                new_name = re.sub(r'\.(heic|heif)$', '.jpg', original_name, flags=re.IGNORECASE)
                new_file = ContentFile(output.getvalue(), name=new_name)
                
                logger.info(f"Imagen HEIC convertida: {original_name} -> {new_name}")
                return new_file, original_format, True
                
            except Exception as e:
                logger.error(f"Error convirtiendo HEIC {original_name}: {e}")
                # Si falla la conversión, devolver el archivo original
                return image_file, original_format, False
        
        # Si no es HEIC o no queremos convertir, devolver original
        return image_file, original_format, False
        
    except Exception as e:
        logger.error(f"Error procesando imagen {image_file.name}: {e}")
        return image_file, 'unknown', False


def validate_image_file(image_file, max_size_mb=10):
    """
    Valida un archivo de imagen
    
    Args:
        image_file: Archivo de imagen
        max_size_mb: Tamaño máximo en MB
    
    Returns:
        tuple: (es_válido, mensaje_error)
    """
    try:
        # Verificar tamaño
        max_size_bytes = max_size_mb * 1024 * 1024
        if image_file.size > max_size_bytes:
            return False, f"El archivo es demasiado grande. Máximo {max_size_mb}MB"
        
        # Verificar formato
        allowed_formats = ['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif']
        file_extension = os.path.splitext(image_file.name)[1].lower().lstrip('.')
        
        if file_extension not in allowed_formats:
            return False, f"Formato no permitido. Formatos válidos: {', '.join(allowed_formats)}"
        
        # Verificar que es realmente una imagen
        try:
            image = PILImage.open(image_file)
            image.verify()
        except Exception:
            return False, "El archivo no es una imagen válida"
        
        return True, None
        
    except Exception as e:
        logger.error(f"Error validando imagen: {e}")
        return False, "Error validando el archivo"


def generate_image_thumbnail(image_path, size=(300, 300)):
    """
    Genera un thumbnail de una imagen
    
    Args:
        image_path: Ruta a la imagen
        size: Tamaño del thumbnail (ancho, alto)
    
    Returns:
        str: Ruta al thumbnail generado
    """
    try:
        # Esta función se puede implementar con django-imagekit
        # Por ahora devolvemos la imagen original
        return image_path
    except Exception as e:
        logger.error(f"Error generando thumbnail: {e}")
        return image_path


def clean_image_filename(filename):
    """
    Limpia el nombre de archivo de una imagen
    
    Args:
        filename: Nombre original del archivo
    
    Returns:
        str: Nombre limpio
    """
    # Obtener nombre y extensión
    name, ext = os.path.splitext(filename)
    
    # Limpiar nombre (solo letras, números, guiones y guiones bajos)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    # Limitar longitud
    clean_name = clean_name[:50]
    
    return f"{clean_name}{ext}"


def get_image_metadata(image_path):
    """
    Obtiene metadatos de una imagen
    
    Args:
        image_path: Ruta a la imagen
    
    Returns:
        dict: Metadatos de la imagen
    """
    try:
        with PILImage.open(image_path) as img:
            return {
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'mode': img.mode,
                'has_transparency': img.mode in ('RGBA', 'LA', 'P') and 'transparency' in img.info,
            }
    except Exception as e:
        logger.error(f"Error obteniendo metadatos de {image_path}: {e}")
        return {}