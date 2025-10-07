"""
Comando para probar emails de moderación con tokens de aprobación/rechazo
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from videosvoley.videos.models import Image, Match
from videosvoley.core.email_utils import send_notification_email
from videosvoley.core.moderation_views import generate_moderation_token
import os

User = get_user_model()


class Command(BaseCommand):
    help = 'Envía emails de prueba para moderación con botones de acción'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            help='Tipo de email: user o image',
            choices=['user', 'image'],
            default='user'
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Email de destino (opcional, por defecto usa superusers)',
            default=None
        )

    def handle(self, *args, **options):
        email_type = options['type']
        recipient_email = options['email']
        
        # Preparar lista de destinatarios
        recipient_list = [recipient_email] if recipient_email else None
        
        if email_type == 'user':
            self.test_user_pending_email(recipient_list)
        elif email_type == 'image':
            self.test_image_pending_email(recipient_list)

    def test_user_pending_email(self, recipient_list=None):
        """Envía email de prueba para usuario pendiente"""
        self.stdout.write(self.style.WARNING('Enviando email de prueba: Nuevo usuario pendiente...'))
        
        # Buscar o crear usuario de prueba
        test_user, created = User.objects.get_or_create(
            username='test_pendiente',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Usuario',
                'last_name': 'de Prueba',
                'is_approved': False,
                'parent_info': 'Papá de Pedrito de Infantil'
            }
        )
        
        if not created:
            # Actualizar para que esté pendiente
            test_user.is_approved = False
            test_user.save()
            self.stdout.write(self.style.SUCCESS(f'Usuario existente actualizado: {test_user.username}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Usuario de prueba creado: {test_user.username}'))
        
        # Generar tokens
        approve_token = generate_moderation_token('user', test_user.id, 'approve')
        reject_token = generate_moderation_token('user', test_user.id, 'reject')
        
        # Simular URLs absolutas
        base_url = 'http://localhost:8000'
        
        context = {
            'user': test_user,
            'site_name': 'VideosVoley',
            'admin_url': f'{base_url}/admin/users/user/{test_user.id}/change/',
            'approve_url': f'{base_url}/moderate/user/{approve_token}/',
            'reject_url': f'{base_url}/moderate/user/{reject_token}/',
            'is_oauth': False,
        }
        
        success = send_notification_email(
            subject=f'[TEST] Nuevo usuario pendiente de aprobación: {test_user.username}',
            template_name='emails/new_user_pending.html',
            context=context,
            recipient_list=recipient_list
        )
        
        if success:
            self.stdout.write(self.style.SUCCESS('✓ Email enviado correctamente'))
            self.stdout.write(self.style.WARNING('\nURLs de prueba:'))
            self.stdout.write(f'  Aprobar: {base_url}/moderate/user/{approve_token}/')
            self.stdout.write(f'  Rechazar: {base_url}/moderate/user/{reject_token}/')
        else:
            self.stdout.write(self.style.ERROR('✗ Error al enviar el email'))
            self.stdout.write(self.style.WARNING('Verifica NOTIFICATION_EMAIL_ENABLED en settings'))

    def test_image_pending_email(self, recipient_list=None):
        """Envía email de prueba para imagen pendiente"""
        self.stdout.write(self.style.WARNING('Enviando email de prueba: Nueva imagen pendiente...'))
        
        # Buscar una imagen pendiente o la más reciente
        test_image = Image.objects.filter(status='pending').first()
        
        if not test_image:
            # Si no hay imágenes pendientes, usar cualquier imagen
            test_image = Image.objects.first()
            if not test_image:
                self.stdout.write(self.style.ERROR('✗ No hay imágenes en el sistema para probar'))
                self.stdout.write(self.style.WARNING('Sube una imagen primero desde /videos/images/upload/'))
                return
            
            # Cambiar temporalmente a pendiente para la prueba
            test_image.status = 'pending'
            test_image.save()
            self.stdout.write(self.style.SUCCESS(f'Imagen actualizada a pendiente: {test_image.title}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Imagen pendiente encontrada: {test_image.title}'))
        
        # Generar tokens
        approve_token = generate_moderation_token('image', test_image.id, 'approve')
        reject_token = generate_moderation_token('image', test_image.id, 'reject')
        
        # Simular URLs absolutas
        base_url = 'http://localhost:8000'
        
        # Preparar imagen embebida y adjunta
        embedded_images = {}
        attachments = []
        if test_image.image:
            try:
                image_path = test_image.image.path
                if os.path.exists(image_path):
                    # Embeber en el HTML
                    embedded_images['pending_image'] = image_path
                    # También adjuntar
                    attachments.append(image_path)
                    self.stdout.write(self.style.SUCCESS(f'✓ Imagen embebida y adjunta: {os.path.basename(image_path)}'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠ No se pudo procesar imagen: {str(e)}'))
        
        context = {
            'image': test_image,
            'user': test_image.uploaded_by,
            'site_name': 'VideosVoley',
            'admin_url': f'{base_url}/admin/videos/image/{test_image.id}/change/',
            'image_cid': 'pending_image' if embedded_images else None,
            'approve_url': f'{base_url}/moderate/image/{approve_token}/',
            'reject_url': f'{base_url}/moderate/image/{reject_token}/',
        }
        
        success = send_notification_email(
            subject=f'[TEST] Nueva imagen pendiente de moderación: {test_image.title}',
            template_name='emails/image_pending.html',
            context=context,
            recipient_list=recipient_list,
            attachments=attachments if attachments else None,
            embedded_images=embedded_images if embedded_images else None
        )
        
        if success:
            self.stdout.write(self.style.SUCCESS('✓ Email enviado correctamente'))
            self.stdout.write(self.style.WARNING('\nURLs de prueba:'))
            self.stdout.write(f'  Aprobar: {base_url}/moderate/image/{approve_token}/')
            self.stdout.write(f'  Rechazar: {base_url}/moderate/image/{reject_token}/')
        else:
            self.stdout.write(self.style.ERROR('✗ Error al enviar el email'))
            self.stdout.write(self.style.WARNING('Verifica NOTIFICATION_EMAIL_ENABLED en settings'))

