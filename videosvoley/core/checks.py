"""
System checks para validar configuración de producción
"""
from django.core.checks import Warning, register, Tags
from django.conf import settings
import os


@register(Tags.compatibility)
def check_google_vision_config(app_configs, **kwargs):
    """Verificar configuración de Google Vision API"""
    warnings = []
    
    if settings.GOOGLE_VISION_ENABLED:
        creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        if not creds_path:
            warnings.append(
                Warning(
                    'Google Vision API está habilitada pero GOOGLE_APPLICATION_CREDENTIALS no está configurado',
                    hint='Configure GOOGLE_APPLICATION_CREDENTIALS en .env con la ruta al archivo de credenciales JSON',
                    id='videosvoley.W001',
                )
            )
        elif not os.path.exists(creds_path):
            warnings.append(
                Warning(
                    f'Google Vision API está habilitada pero el archivo de credenciales no existe: {creds_path}',
                    hint='Verifique que el archivo existe y la ruta es correcta',
                    id='videosvoley.W002',
                )
            )
        else:
            # Verificar que el archivo es legible
            try:
                with open(creds_path, 'r') as f:
                    import json
                    json.load(f)
            except Exception as e:
                warnings.append(
                    Warning(
                        f'Error al leer archivo de credenciales de Google Vision: {e}',
                        hint='Verifique que el archivo JSON es válido y tiene los permisos correctos',
                        id='videosvoley.W003',
                    )
                )
    
    return warnings


@register(Tags.compatibility)
def check_socialauth_config(app_configs, **kwargs):
    """Verificar configuración de django-allauth y Sites"""
    warnings = []
    
    from django.contrib.sites.models import Site
    
    try:
        site = Site.objects.get(id=settings.SITE_ID)
        
        # Verificar que el dominio no sea el por defecto
        if site.domain in ['example.com', 'localhost', '127.0.0.1']:
            warnings.append(
                Warning(
                    f'Site domain está configurado como "{site.domain}" - esto puede causar problemas con OAuth en producción',
                    hint='Actualizar el dominio: python manage.py shell -> Site.objects.get(id=1).update(domain="tu-dominio.com")',
                    id='videosvoley.W004',
                )
            )
        
        # Verificar que hay al menos una SocialApp configurada
        try:
            from allauth.socialaccount.models import SocialApp
            google_apps = SocialApp.objects.filter(provider='google')
            
            if not google_apps.exists():
                warnings.append(
                    Warning(
                        'No hay aplicaciones de Google OAuth configuradas',
                        hint='Configurar en /admin/socialaccount/socialapp/',
                        id='videosvoley.W005',
                    )
                )
            else:
                # Verificar que el site actual está asociado
                for app in google_apps:
                    if not app.sites.filter(id=settings.SITE_ID).exists():
                        warnings.append(
                            Warning(
                                f'La aplicación de Google OAuth "{app.name}" no está asociada al site actual',
                                hint=f'Añadir el site "{site.domain}" a la aplicación en /admin/socialaccount/socialapp/{app.id}/change/',
                                id='videosvoley.W006',
                            )
                        )
        except ImportError:
            pass  # allauth no instalado
            
    except Site.DoesNotExist:
        warnings.append(
            Warning(
                f'Site con ID {settings.SITE_ID} no existe en la base de datos',
                hint='Ejecutar: python manage.py migrate',
                id='videosvoley.W007',
            )
        )
    except Exception as e:
        # Si hay error de base de datos (ej: durante migraciones), ignorar
        pass
    
    return warnings


@register(Tags.compatibility)
def check_media_permissions(app_configs, **kwargs):
    """Verificar permisos del directorio MEDIA_ROOT"""
    warnings = []
    
    media_root = settings.MEDIA_ROOT
    
    if not os.path.exists(media_root):
        warnings.append(
            Warning(
                f'MEDIA_ROOT no existe: {media_root}',
                hint='Crear el directorio: mkdir -p ' + media_root,
                id='videosvoley.W008',
            )
        )
    elif not os.access(media_root, os.W_OK):
        warnings.append(
            Warning(
                f'MEDIA_ROOT no tiene permisos de escritura: {media_root}',
                hint='Corregir permisos: chmod 755 ' + media_root,
                id='videosvoley.W009',
            )
        )
    
    return warnings


@register(Tags.compatibility)
def check_email_config(app_configs, **kwargs):
    """Verificar configuración de email"""
    warnings = []
    
    if settings.NOTIFICATION_EMAIL_ENABLED:
        if not settings.EMAIL_HOST_USER:
            warnings.append(
                Warning(
                    'Las notificaciones por email están habilitadas pero EMAIL_HOST_USER no está configurado',
                    hint='Configure EMAIL_HOST_USER en .env',
                    id='videosvoley.W010',
                )
            )
        
        if not settings.ADMIN_EMAIL_LIST:
            warnings.append(
                Warning(
                    'Las notificaciones por email están habilitadas pero ADMIN_EMAIL_LIST está vacío',
                    hint='Configure ADMIN_EMAIL_LIST en .env con emails separados por comas',
                    id='videosvoley.W011',
                )
            )
    
    return warnings