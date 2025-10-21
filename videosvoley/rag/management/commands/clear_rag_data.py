from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from videosvoley.rag.models import Document, ChatSession, ChatMessage
from videosvoley.rag.services import get_rag_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Limpiar todos los datos del sistema RAG'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirmar la eliminación (requerido para ejecutar)'
        )
        parser.add_argument(
            '--keep-chat',
            action='store_true',
            help='Mantener conversaciones de chat'
        )
        parser.add_argument(
            '--keep-documents',
            action='store_true',
            help='Mantener documentos en la base de datos'
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'Esta acción eliminará todos los datos del sistema RAG.\n'
                    'Usa --confirm para proceder.'
                )
            )
            return

        try:
            with transaction.atomic():
                # Limpiar ChromaDB
                self.stdout.write('Limpiando ChromaDB...')
                try:
                    # Obtener todos los IDs de documentos
                    document_ids = list(Document.objects.values_list('id', flat=True))
                    
                    if document_ids:
                        # Eliminar de ChromaDB
                        rag_service = get_rag_service()
                        rag_service.collection.delete(ids=[str(doc_id) for doc_id in document_ids])
                        self.stdout.write(f'Eliminados {len(document_ids)} documentos de ChromaDB')
                    else:
                        self.stdout.write('No hay documentos en ChromaDB para eliminar')
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Error limpiando ChromaDB: {e}')
                    )

                # Limpiar conversaciones de chat
                if not options['keep_chat']:
                    self.stdout.write('Limpiando conversaciones de chat...')
                    chat_count = ChatMessage.objects.count()
                    session_count = ChatSession.objects.count()
                    
                    ChatMessage.objects.all().delete()
                    ChatSession.objects.all().delete()
                    
                    self.stdout.write(f'Eliminadas {session_count} sesiones y {chat_count} mensajes')
                else:
                    self.stdout.write('Manteniendo conversaciones de chat...')

                # Limpiar documentos
                if not options['keep_documents']:
                    self.stdout.write('Limpiando documentos...')
                    doc_count = Document.objects.count()
                    Document.objects.all().delete()
                    self.stdout.write(f'Eliminados {doc_count} documentos')
                else:
                    self.stdout.write('Manteniendo documentos en la base de datos...')
                    # Solo marcar como no indexados
                    Document.objects.update(is_indexed=False)
                    self.stdout.write('Marcados todos los documentos como no indexados')

            self.stdout.write(
                self.style.SUCCESS('Limpieza completada exitosamente')
            )

        except Exception as e:
            logger.error(f"Error en limpieza: {e}")
            raise CommandError(f'Error durante la limpieza: {e}')