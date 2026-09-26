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
                    id='ilovevoley.W001',
                )
            )
        elif not os.path.exists(creds_path):
            warnings.append(
                Warning(
                    f'Google Vision API está habilitada pero el archivo de credenciales no existe: {creds_path}',
                    hint='Verifique que el archivo existe y la ruta es correcta',
                    id='ilovevoley.W002',
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
                        id='ilovevoley.W003',
                    )
                )
    
    return warnings


@register(Tags.compatibility, deploy=True)
def check_socialauth_config(app_configs, databases=None, **kwargs):
    """Verificar configuración de django-allauth y Sites en despliegue"""
    warnings = []

    from django.contrib.sites.models import Site
    from django.db import connections, router
    from django.db.utils import DatabaseError

    site_db = router.db_for_read(Site)
    if databases is not None and site_db not in databases:
        return []

    conn = connections[site_db]
    try:
        with conn.cursor() as cursor:
            tables = set(conn.introspection.table_names(cursor))
    except DatabaseError:
        return warnings

    site_table = Site._meta.db_table
    if site_table not in tables:
        warnings.append(
            Warning(
                f'La tabla de Sites ({site_table}) no existe en la base de datos',
                hint='Ejecutar: python manage.py migrate',
                id='ilovevoley.W007',
            )
        )
        return warnings

    try:
        site = Site.objects.using(site_db).get(id=settings.SITE_ID)
    except Site.DoesNotExist:
        warnings.append(
            Warning(
                f'Site con ID {settings.SITE_ID} no existe en la base de datos',
                hint='Ejecutar: python manage.py migrate',
                id='ilovevoley.W007',
            )
        )
        return warnings
    except DatabaseError:
        return warnings

    # Verificar que el dominio no sea el por defecto
    if site.domain in ['example.com', 'localhost', '127.0.0.1']:
        warnings.append(
            Warning(
                f'Site domain está configurado como "{site.domain}" - esto puede causar problemas con OAuth en producción',
                hint='Actualizar el dominio: python manage.py shell -> Site.objects.get(id=1).update(domain="tu-dominio.com")',
                id='ilovevoley.W004',
            )
        )

    # Verificar que hay al menos una SocialApp configurada
    try:
        from allauth.socialaccount.models import SocialApp

        social_db = router.db_for_read(SocialApp)
        if databases is not None and social_db not in databases:
            return warnings

        social_conn = connections[social_db]
        try:
            with social_conn.cursor() as cursor:
                social_tables = set(social_conn.introspection.table_names(cursor))
        except DatabaseError:
            return warnings

        app_table = SocialApp._meta.db_table
        if app_table not in social_tables:
            return warnings

        google_apps = list(SocialApp.objects.using(social_db).filter(provider='google'))

        if not google_apps:
            warnings.append(
                Warning(
                    'No hay aplicaciones de Google OAuth configuradas',
                    hint='Configurar en /admin/socialaccount/socialapp/',
                    id='ilovevoley.W005',
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
                            id='ilovevoley.W006',
                        )
                    )
    except ImportError:
        pass  # allauth no instalado
    except DatabaseError:
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
                id='ilovevoley.W008',
            )
        )
    elif not os.access(media_root, os.W_OK):
        warnings.append(
            Warning(
                f'MEDIA_ROOT no tiene permisos de escritura: {media_root}',
                hint='Corregir permisos: chmod 755 ' + media_root,
                id='ilovevoley.W009',
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
                    id='ilovevoley.W010',
                )
            )
        
        if not settings.ADMIN_EMAIL_LIST:
            warnings.append(
                Warning(
                    'Las notificaciones por email están habilitadas pero ADMIN_EMAIL_LIST está vacío',
                    hint='Configure ADMIN_EMAIL_LIST en .env con emails separados por comas',
                    id='ilovevoley.W011',
                )
            )
    
    return warnings