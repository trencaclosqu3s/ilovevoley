"""
Comando para verificar la configuración de producción
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.sites.models import Site
import os


class Command(BaseCommand):
    help = 'Verifica la configuración de producción y detecta problemas comunes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix-site',
            action='store_true',
            help='Actualizar automáticamente el dominio del Site si es necesario',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  Verificación de Configuración de Producción'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        errors = 0
        warnings = 0
        
        # 1. Verificar Site
        self.stdout.write('\n' + self.style.HTTP_INFO('1. Django Sites Framework'))
        self.stdout.write('-' * 60)
        try:
            site = Site.objects.get(id=settings.SITE_ID)
            self.stdout.write(f'  Site ID: {site.id}')
            self.stdout.write(f'  Domain: {site.domain}')
            self.stdout.write(f'  Name: {site.name}')
            
            if site.domain in ['example.com', 'localhost', '127.0.0.1']:
                self.stdout.write(self.style.WARNING(f'  ⚠ ADVERTENCIA: Domain parece ser de desarrollo'))
                warnings += 1
                
                if options['fix_site']:
                    new_domain = input('  Ingrese el dominio de producción (ej: midominio.com): ')
                    if new_domain:
                        site.domain = new_domain
                        site.save()
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Domain actualizado a: {new_domain}'))
            else:
                self.stdout.write(self.style.SUCCESS('  ✓ Domain configurado correctamente'))
                
        except Site.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'  ✗ ERROR: Site con ID {settings.SITE_ID} no existe'))
            errors += 1
        
        # 2. Verificar Google OAuth
        self.stdout.write('\n' + self.style.HTTP_INFO('2. Google OAuth (django-allauth)'))
        self.stdout.write('-' * 60)
        try:
            from allauth.socialaccount.models import SocialApp
            google_apps = SocialApp.objects.filter(provider='google')
            
            if google_apps.exists():
                for app in google_apps:
                    self.stdout.write(f'  App: {app.name}')
                    self.stdout.write(f'    Client ID: {app.client_id[:20]}...')
                    self.stdout.write(f'    Secret configurado: {"Sí" if app.secret else "No"}')
                    
                    app_sites = list(app.sites.all())
                    if app_sites:
                        self.stdout.write(f'    Sites asociados: {", ".join([s.domain for s in app_sites])}')
                    else:
                        self.stdout.write(self.style.ERROR('    ✗ ERROR: No hay sites asociados'))
                        errors += 1
                    
                    if not app.sites.filter(id=settings.SITE_ID).exists():
                        self.stdout.write(self.style.WARNING(f'    ⚠ ADVERTENCIA: Site actual ({site.domain}) no está asociado'))
                        warnings += 1
                    else:
                        self.stdout.write(self.style.SUCCESS('    ✓ Site actual está asociado'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠ ADVERTENCIA: No hay apps de Google OAuth configuradas'))
                self.stdout.write('    Configurar en: /admin/socialaccount/socialapp/')
                warnings += 1
                
        except ImportError:
            self.stdout.write(self.style.WARNING('  ⚠ django-allauth no está instalado'))
            warnings += 1
        
        # 3. Verificar Google Vision
        self.stdout.write('\n' + self.style.HTTP_INFO('3. Google Vision API'))
        self.stdout.write('-' * 60)
        
        vision_enabled = settings.GOOGLE_VISION_ENABLED
        self.stdout.write(f'  Estado: {"Habilitada" if vision_enabled else "Deshabilitada"}')
        
        if vision_enabled:
            creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS
            self.stdout.write(f'  Ruta credenciales: {creds_path}')
            
            if not creds_path:
                self.stdout.write(self.style.ERROR('  ✗ ERROR: GOOGLE_APPLICATION_CREDENTIALS no configurado'))
                errors += 1
            elif not os.path.exists(creds_path):
                self.stdout.write(self.style.ERROR(f'  ✗ ERROR: Archivo de credenciales no existe'))
                errors += 1
            else:
                # Verificar que es un JSON válido
                try:
                    import json
                    with open(creds_path, 'r') as f:
                        creds = json.load(f)
                        if 'type' in creds and 'project_id' in creds:
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Credenciales válidas (proyecto: {creds.get("project_id", "N/A")})'))
                        else:
                            self.stdout.write(self.style.WARNING('  ⚠ Archivo JSON no parece ser de credenciales de Google'))
                            warnings += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  ✗ ERROR: No se puede leer credenciales: {e}'))
                    errors += 1
            
            # Probar importar la librería
            try:
                from google.cloud import vision
                self.stdout.write(self.style.SUCCESS('  ✓ Librería google-cloud-vision instalada'))
                
                # Intentar crear cliente (solo si hay credenciales)
                if creds_path and os.path.exists(creds_path):
                    try:
                        client = vision.ImageAnnotatorClient()
                        self.stdout.write(self.style.SUCCESS('  ✓ Cliente de Vision API creado correctamente'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'  ✗ ERROR al crear cliente: {e}'))
                        errors += 1
                        
            except ImportError:
                self.stdout.write(self.style.ERROR('  ✗ ERROR: google-cloud-vision no está instalada'))
                self.stdout.write('    Instalar con: pip install google-cloud-vision==3.8.0')
                errors += 1
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ Vision API deshabilitada (las imágenes requerirán moderación manual)'))
        
        # 4. Verificar permisos de media
        self.stdout.write('\n' + self.style.HTTP_INFO('4. Directorio MEDIA_ROOT'))
        self.stdout.write('-' * 60)
        
        media_root = settings.MEDIA_ROOT
        self.stdout.write(f'  Ruta: {media_root}')
        
        if os.path.exists(media_root):
            self.stdout.write(self.style.SUCCESS('  ✓ Directorio existe'))
            
            if os.access(media_root, os.W_OK):
                self.stdout.write(self.style.SUCCESS('  ✓ Permisos de escritura: OK'))
            else:
                self.stdout.write(self.style.ERROR('  ✗ ERROR: Sin permisos de escritura'))
                self.stdout.write(f'    Corregir con: sudo chown -R $USER:$USER {media_root}')
                errors += 1
                
            # Verificar subdirectorios
            for subdir in ['images', 'avatars']:
                subdir_path = os.path.join(media_root, subdir)
                if os.path.exists(subdir_path):
                    self.stdout.write(f'  ✓ Subdirectorio {subdir}/ existe')
                else:
                    self.stdout.write(self.style.WARNING(f'  ⚠ Subdirectorio {subdir}/ no existe (se creará automáticamente)'))
                    warnings += 1
        else:
            self.stdout.write(self.style.ERROR('  ✗ ERROR: Directorio no existe'))
            self.stdout.write(f'    Crear con: mkdir -p {media_root}')
            errors += 1
        
        # 5. Verificar configuración de email
        self.stdout.write('\n' + self.style.HTTP_INFO('5. Configuración de Email'))
        self.stdout.write('-' * 60)
        
        email_enabled = settings.NOTIFICATION_EMAIL_ENABLED
        self.stdout.write(f'  Notificaciones: {"Habilitadas" if email_enabled else "Deshabilitadas"}')
        
        if email_enabled:
            self.stdout.write(f'  Host: {settings.EMAIL_HOST}')
            self.stdout.write(f'  Puerto: {settings.EMAIL_PORT}')
            self.stdout.write(f'  TLS: {settings.EMAIL_USE_TLS}')
            
            if settings.EMAIL_HOST_USER:
                self.stdout.write(f'  Usuario: {settings.EMAIL_HOST_USER}')
                self.stdout.write(self.style.SUCCESS('  ✓ EMAIL_HOST_USER configurado'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠ EMAIL_HOST_USER no configurado'))
                warnings += 1
            
            if settings.ADMIN_EMAIL_LIST:
                self.stdout.write(f'  Admins: {len(settings.ADMIN_EMAIL_LIST)} email(s) configurados')
                self.stdout.write(self.style.SUCCESS('  ✓ ADMIN_EMAIL_LIST configurado'))
            else:
                self.stdout.write(self.style.WARNING('  ⚠ ADMIN_EMAIL_LIST vacío'))
                warnings += 1
        else:
            self.stdout.write('  (Notificaciones deshabilitadas)')
        
        # 6. Verificar configuración de seguridad
        self.stdout.write('\n' + self.style.HTTP_INFO('6. Configuración de Seguridad'))
        self.stdout.write('-' * 60)
        
        self.stdout.write(f'  DEBUG: {settings.DEBUG}')
        if settings.DEBUG:
            self.stdout.write(self.style.WARNING('  ⚠ ADVERTENCIA: DEBUG está activado en producción'))
            warnings += 1
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ DEBUG desactivado'))
        
        self.stdout.write(f'  ALLOWED_HOSTS: {", ".join(settings.ALLOWED_HOSTS)}')
        if not settings.ALLOWED_HOSTS or settings.ALLOWED_HOSTS == ['*']:
            self.stdout.write(self.style.WARNING('  ⚠ ALLOWED_HOSTS no está configurado correctamente'))
            warnings += 1
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ ALLOWED_HOSTS configurado'))
        
        csrf_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
        self.stdout.write(f'  CSRF_TRUSTED_ORIGINS: {", ".join(csrf_origins) if csrf_origins else "No configurado"}')
        if not csrf_origins:
            self.stdout.write(self.style.WARNING('  ⚠ CSRF_TRUSTED_ORIGINS no configurado'))
            warnings += 1
        else:
            self.stdout.write(self.style.SUCCESS('  ✓ CSRF_TRUSTED_ORIGINS configurado'))
        
        # Resumen final
        self.stdout.write('\n' + self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('  Resumen'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        if errors == 0 and warnings == 0:
            self.stdout.write(self.style.SUCCESS('\n  ✓ ¡Todo está configurado correctamente!'))
        else:
            if errors > 0:
                self.stdout.write(self.style.ERROR(f'\n  ✗ {errors} error(es) encontrado(s)'))
            if warnings > 0:
                self.stdout.write(self.style.WARNING(f'  ⚠ {warnings} advertencia(s) encontrada(s)'))
            
            self.stdout.write('\n  Revisa los mensajes anteriores para más detalles.')
        
        self.stdout.write('')