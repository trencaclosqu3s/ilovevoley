from django.core.management.base import BaseCommand
from videosvoley.rag.services import get_rag_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Probar el sistema RAG'

    def handle(self, *args, **options):
        try:
            self.stdout.write('Probando sistema RAG...')
            
            # Obtener servicio RAG
            rag_service = get_rag_service()
            
            # Probar estadísticas
            stats = rag_service.get_collection_stats()
            self.stdout.write(f'✅ ChromaDB conectado: {stats["collection_name"]}')
            self.stdout.write(f'✅ Documentos en colección: {stats["total_documents"]}')
            
            # Probar búsqueda (aunque no haya documentos)
            results = rag_service.search_similar_documents("test", n_results=1)
            self.stdout.write(f'✅ Búsqueda funcionando: {len(results)} resultados')
            
            self.stdout.write(
                self.style.SUCCESS('Sistema RAG funcionando correctamente')
            )
            
        except Exception as e:
            logger.error(f"Error probando RAG: {e}")
            self.stdout.write(
                self.style.ERROR(f'Error en sistema RAG: {e}')
            )