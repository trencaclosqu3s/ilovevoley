from django.core.management.base import BaseCommand
from django.core.exceptions import ImproperlyConfigured
from videosvoley.rag.services import get_rag_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Inicializar el sistema RAG (crear colección ChromaDB)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar recreación de la colección'
        )

    def handle(self, *args, **options):
        force = options['force']
        
        try:
            self.stdout.write('Inicializando sistema RAG...')
            
            # Obtener servicio RAG (esto creará la colección si no existe)
            rag_service = get_rag_service()
            
            if force:
                self.stdout.write('Forzando recreación de la colección...')
                try:
                    # Eliminar colección existente
                    rag_service.chroma_client.delete_collection(rag_service.collection_name)
                    self.stdout.write(f'Colección {rag_service.collection_name} eliminada')
                except Exception as e:
                    self.stdout.write(f'No se pudo eliminar la colección: {e}')
                
                # Crear nueva colección
                rag_service.collection = rag_service.chroma_client.create_collection(
                    name=rag_service.collection_name,
                    metadata={"description": "Documentos de VideosVoley para RAG"}
                )
                self.stdout.write(f'Colección {rag_service.collection_name} recreada')
            
            # Verificar que la colección existe
            stats = rag_service.get_collection_stats()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Sistema RAG inicializado correctamente.\n'
                    f'Colección: {stats["collection_name"]}\n'
                    f'Documentos: {stats["total_documents"]}'
                )
            )
            
        except ImproperlyConfigured as e:
            self.stdout.write(
                self.style.ERROR(f'Error de configuración: {e}')
            )
        except Exception as e:
            logger.error(f"Error inicializando RAG: {e}")
            self.stdout.write(
                self.style.ERROR(f'Error inicializando sistema RAG: {e}')
            )