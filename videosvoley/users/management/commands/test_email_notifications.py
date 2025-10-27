from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from videosvoley.content.models import Image, Category
from videosvoley.competitions.models import Match
from videosvoley.core.middleware import send_404_daily_report
from videosvoley.core.email_utils import get_admin_emails
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Prueba el sistema de notificaciones por email'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-type',
            type=str,
            choices=['all', 'user', 'image', '404', 'config'],
            default='config',
            help='Tipo de prueba a ejecutar'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email específico para pruebas (opcional)'
        )

    def handle(self, *args, **options):
        test_type = options['test_type']
        test_email = options.get('email')

        self.stdout.write(
            self.style.SUCCESS('🧪 Iniciando pruebas del sistema de notificaciones por email')
        )

        # Verificar configuración básica
        if test_type in ['all', 'config']:
            self.test_email_config()

        # Probar notificaciones de usuario
        if test_type in ['all', 'user']:
            self.test_user_notifications(test_email)

        # Probar notificaciones de imagen
        if test_type in ['all', 'image']:
            self.test_image_notifications(test_email)

        # Probar notificaciones 404
        if test_type in ['all', '404']:
            self.test_404_notifications()

        self.stdout.write(
            self.style.SUCCESS('✅ Pruebas completadas')
        )

    def test_email_config(self):
        """Verifica la configuración de email"""
        self.stdout.write(
            self.style.WARNING('📧 Verificando configuración de email...')
        )

        # Obtener emails de admins
        admin_emails = get_admin_emails()
        
        # Verificar variables básicas
        config_items = [
            ('EMAIL_BACKEND', settings.EMAIL_BACKEND),
            ('EMAIL_HOST', settings.EMAIL_HOST),
            ('EMAIL_PORT', settings.EMAIL_PORT),
            ('EMAIL_USE_TLS', settings.EMAIL_USE_TLS),
            ('EMAIL_HOST_USER', settings.EMAIL_HOST_USER),
            ('DEFAULT_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL),
            ('NOTIFICATION_EMAIL_ENABLED', settings.NOTIFICATION_EMAIL_ENABLED),
            ('ADMIN_EMAILS (superusers)', ', '.join(admin_emails) if admin_emails else 'No hay superusers con email'),
        ]

        for key, value in config_items:
            if value:
                self.stdout.write(f"  ✅ {key}: {value}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ {key}: No configurado")
                )

        # Verificar configuración de notificaciones
        self.stdout.write("\n📋 Configuración de notificaciones:")
        for key, value in settings.EMAIL_NOTIFICATIONS.items():
            status = "✅ Activado" if value else "⚠️ Desactivado"
            self.stdout.write(f"  {status} {key}")

        # Probar envío básico
        if settings.NOTIFICATION_EMAIL_ENABLED and admin_emails:
            self.stdout.write("\n📤 Probando envío de email básico...")
            try:
                send_mail(
                    subject='[PRUEBA] Sistema de notificaciones',
                    message='Este es un email de prueba del sistema de notificaciones.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=admin_emails,
                    fail_silently=False,
                )
                self.stdout.write(
                    self.style.SUCCESS("  ✅ Email de prueba enviado correctamente")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ❌ Error enviando email: {str(e)}")
                )
        else:
            self.stdout.write(
                self.style.WARNING("  ⚠️ Email no configurado o no hay superusers con email")
            )

    def test_user_notifications(self, test_email=None):
        """Prueba las notificaciones de usuario"""
        self.stdout.write(
            self.style.WARNING('\n👤 Probando notificaciones de usuario...')
        )

        if not settings.NOTIFICATION_EMAIL_ENABLED:
            self.stdout.write(
                self.style.WARNING("  ⚠️ Notificaciones deshabilitadas, saltando pruebas")
            )
            return

        # Buscar un usuario de prueba
        try:
            test_user = User.objects.filter(is_approved=False).first()
            if not test_user:
                self.stdout.write("  📝 Creando usuario de prueba...")
                test_user = User.objects.create_user(
                    username=f'test_user_{random.randint(1000, 9999)}',
                    email=test_email or 'test@example.com',
                    is_approved=False
                )

            # Simular notificación de usuario pendiente
            self.stdout.write("  📧 Probando notificación de usuario pendiente...")
            context = {
                'user': test_user,
                'site_name': 'I Love Voley (PRUEBA)',
                'admin_url': f'/admin/users/user/{test_user.id}/change/',
                'is_oauth': False,
            }
            
            html_message = render_to_string('emails/new_user_pending.html', context)
            plain_message = strip_tags(html_message)
            
            recipient_list = [test_email] if test_email else get_admin_emails()
            
            send_mail(
                subject='[PRUEBA] Nuevo usuario pendiente de aprobación',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
            )
            
            self.stdout.write(
                self.style.SUCCESS("  ✅ Notificación de usuario pendiente enviada")
            )

            # Simular notificación de usuario aprobado
            if test_user.email:
                self.stdout.write("  📧 Probando notificación de usuario aprobado...")
                context = {
                    'user': test_user,
                    'site_name': 'I Love Voley (PRUEBA)',
                    'site_url': 'http://localhost:8000',
                }
                
                html_message = render_to_string('emails/user_approved.html', context)
                plain_message = strip_tags(html_message)
                
                send_mail(
                    subject='[PRUEBA] Tu cuenta ha sido aprobada',
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[test_user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                
                self.stdout.write(
                    self.style.SUCCESS("  ✅ Notificación de usuario aprobado enviada")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"  ❌ Error en pruebas de usuario: {str(e)}")
            )

    def test_image_notifications(self, test_email=None):
        """Prueba las notificaciones de imagen"""
        self.stdout.write(
            self.style.WARNING('\n📷 Probando notificaciones de imagen...')
        )

        if not settings.NOTIFICATION_EMAIL_ENABLED:
            self.stdout.write(
                self.style.WARNING("  ⚠️ Notificaciones deshabilitadas, saltando pruebas")
            )
            return

        try:
            # Buscar un usuario para las pruebas
            test_user = User.objects.first()
            if not test_user:
                self.stdout.write(
                    self.style.ERROR("  ❌ No hay usuarios en el sistema para pruebas")
                )
                return

            # Simular notificación de imagen pendiente
            self.stdout.write("  📧 Probando notificación de imagen pendiente...")
            
            # Crear contexto de prueba
            context = {
                'image': {
                    'title': 'Foto de prueba del partido',
                    'description': 'Esta es una imagen de prueba para verificar el sistema de notificaciones.',
                    'get_image_type_display': 'Partido',
                    'tags': 'voleibol, prueba, sistema',
                    'upload_date': '01/01/2024 12:00',
                    'get_status_display': 'Pendiente de Moderación',
                    'id': 999,
                },
                'user': test_user,
                'site_name': 'I Love Voley (PRUEBA)',
                'admin_url': '/admin/videos/image/999/change/',
                'image_url': 'https://via.placeholder.com/400x300?text=Imagen+de+Prueba',
            }
            
            html_message = render_to_string('emails/image_pending.html', context)
            plain_message = strip_tags(html_message)
            
            recipient_list = [test_email] if test_email else get_admin_emails()
            
            send_mail(
                subject='[PRUEBA] Nueva imagen pendiente de moderación',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
            )
            
            self.stdout.write(
                self.style.SUCCESS("  ✅ Notificación de imagen pendiente enviada")
            )

            # Simular notificación de imagen aprobada
            if test_user.email:
                self.stdout.write("  📧 Probando notificación de imagen aprobada...")
                
                context['image']['moderation_date'] = '01/01/2024 14:00'
                context['is_approved'] = True
                context['moderation_notes'] = 'Imagen aprobada - Excelente captura del momento.'
                
                html_message = render_to_string('emails/image_approved.html', context)
                plain_message = strip_tags(html_message)
                
                send_mail(
                    subject='[PRUEBA] Tu imagen ha sido aprobada',
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[test_user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                
                self.stdout.write(
                    self.style.SUCCESS("  ✅ Notificación de imagen aprobada enviada")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"  ❌ Error en pruebas de imagen: {str(e)}")
            )

    def test_404_notifications(self):
        """Prueba las notificaciones de 404"""
        self.stdout.write(
            self.style.WARNING('\n🔍 Probando notificaciones de errores 404...')
        )

        if not settings.NOTIFICATION_EMAIL_ENABLED:
            self.stdout.write(
                self.style.WARNING("  ⚠️ Notificaciones deshabilitadas, saltando pruebas")
            )
            return

        try:
            # Simular reporte diario de 404
            self.stdout.write("  📧 Probando reporte diario de 404...")
            
            # Crear datos de prueba
            context = {
                'date': '01/01/2024',
                'total_errors': 25,
                'unique_urls': 8,
                'site_name': 'I Love Voley (PRUEBA)',
                'top_errors': [
                    ('/videos/antiguo-link/', [
                        {'timestamp': '01/01/2024 10:15:30', 'method': 'GET', 'ip': '192.168.1.100', 'user': 'usuario1'},
                        {'timestamp': '01/01/2024 11:20:15', 'method': 'GET', 'ip': '192.168.1.101', 'user': 'Anonymous'},
                    ]),
                    ('/imagenes/missing.jpg', [
                        {'timestamp': '01/01/2024 09:30:45', 'method': 'GET', 'ip': '192.168.1.102', 'user': 'Anonymous'},
                    ]),
                ]
            }
            
            html_message = render_to_string('emails/404_daily_report.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject='[PRUEBA] Reporte diario de errores 404',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=get_admin_emails(),
                html_message=html_message,
                fail_silently=False,
            )
            
            self.stdout.write(
                self.style.SUCCESS("  ✅ Reporte diario de 404 enviado")
            )

            # Simular alerta de 404
            self.stdout.write("  📧 Probando alerta de 404...")
            
            context = {
                'count': 15,
                'hour': '14:00',
                'site_name': 'I Love Voley (PRUEBA)',
                'last_url': '/videos/no-encontrado/',
            }
            
            html_message = render_to_string('emails/404_alert.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject='[PRUEBA] Alerta: 15 errores 404 en la última hora',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=get_admin_emails(),
                html_message=html_message,
                fail_silently=False,
            )
            
            self.stdout.write(
                self.style.SUCCESS("  ✅ Alerta de 404 enviada")
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"  ❌ Error en pruebas de 404: {str(e)}")
            )