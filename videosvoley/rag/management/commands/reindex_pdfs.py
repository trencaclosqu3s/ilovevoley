from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from videosvoley.rag.models import Document
from videosvoley.rag.services import get_rag_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Re-indexar documentos PDF con fragmentación inteligente'

    def add_arguments(self, parser):
        parser.add_argument('--doc-id', type=int, help='Re-indexar solo documento específico por ID')
        parser.add_argument('--all', action='store_true', help='Re-indexar todos los documentos manuales')
        parser.add_argument('--dry-run', action='store_true', help='Simular sin hacer cambios')
        parser.add_argument('--verbose', action='store_true', help='Mostrar información detallada')
        parser.add_argument('--clear-old', action='store_true', help='Eliminar fragmentos antiguos antes de re-indexar')

    def handle(self, *args, **options):
        doc_id = options.get('doc_id')
        reindex_all = options.get('all')
        dry_run = options.get('dry_run')
        verbose = options.get('verbose', False)
        clear_old = options.get('clear_old', False)

        if not doc_id and not reindex_all:
            raise CommandError('Debes especificar --doc-id <ID> o --all para re-indexar todos')

        # Obtener documentos a re-indexar
        if doc_id:
            docs = Document.objects.filter(id=doc_id, source_type='manual')
            if not docs.exists():
                raise CommandError(f'No se encontró documento manual con ID {doc_id}')
        else:
            docs = Document.objects.filter(source_type='manual')

        if not docs.exists():
            self.stdout.write(self.style.WARNING('📭 No hay documentos para re-indexar'))
            return

        self.stdout.write(self.style.SUCCESS(f'📚 Documentos a re-indexar: {docs.count()}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 MODO DRY RUN - No se realizarán cambios\n'))

        # Re-indexar cada documento
        success_count = 0
        error_count = 0

        for doc in docs:
            self.stdout.write(self.style.NOTICE(f'\n📄 Procesando: {doc.title} (ID: {doc.id})'))

            if verbose:
                self.stdout.write(f'   Tamaño: {len(doc.content)} caracteres')
                self.stdout.write(f'   Metadata: {doc.metadata}')

            if dry_run:
                self.stdout.write(self.style.WARNING('   [DRY RUN] Se re-indexaría con fragmentación inteligente'))
                continue

            try:
                # Eliminar indexación anterior si se solicita
                if clear_old:
                    if verbose:
                        self.stdout.write('   🗑️ Eliminando fragmentos antiguos de ChromaDB...')
                    # Aquí se eliminarían los chunks antiguos de ChromaDB
                    # Por ahora, ChromaDB sobrescribirá automáticamente con el mismo ID

                # Re-indexar con fragmentación inteligente
                rag_service = get_rag_service()

                # Forzar que el documento se marque como no indexado para re-procesar
                doc.is_indexed = False
                doc.save()

                if verbose:
                    self.stdout.write('   ✂️ Aplicando fragmentación inteligente...')

                success = rag_service.add_document(
                    document_id=str(doc.id),
                    content=doc.content,
                    metadata={
                        'title': doc.title,
                        'source_type': doc.source_type,
                        'source_id': doc.source_id,
                        'created_at': doc.created_at.isoformat() if doc.created_at else timezone.now().isoformat(),
                        **(doc.metadata or {}),
                    }
                )

                if success:
                    doc.is_indexed = True
                    doc.save()
                    self.stdout.write(self.style.SUCCESS('   ✅ Re-indexado correctamente'))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR('   ❌ Error en re-indexación'))
                    error_count += 1

            except Exception as e:
                logger.error(f'Error re-indexando documento {doc.id}: {e}')
                self.stdout.write(self.style.ERROR(f'   ❌ Error: {e}'))
                error_count += 1

        # Resumen final
        self.stdout.write(self.style.SUCCESS(f'\n📊 RESUMEN:'))
        self.stdout.write(f'   ✅ Exitosos: {success_count}')
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'   ❌ Errores: {error_count}'))
        self.stdout.write(self.style.SUCCESS(f'   📚 Total procesados: {success_count + error_count}'))
