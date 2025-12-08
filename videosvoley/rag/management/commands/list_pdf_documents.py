from django.core.management.base import BaseCommand
from videosvoley.rag.models import Document


class Command(BaseCommand):
    help = 'Listar todos los documentos PDF indexados en el sistema RAG'

    def add_arguments(self, parser):
        parser.add_argument('--verbose', action='store_true', help='Mostrar información detallada')

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)

        # Consultar documentos manuales (PDFs, reglamentos, etc.)
        docs = Document.objects.filter(source_type='manual').order_by('-created_at')

        if not docs.exists():
            self.stdout.write(self.style.WARNING('📭 No hay documentos PDF indexados en el sistema'))
            return

        self.stdout.write(self.style.SUCCESS(f'📚 Total documentos manuales: {docs.count()}\n'))

        for i, doc in enumerate(docs, 1):
            status = '✅ Indexado' if doc.is_indexed else '❌ No indexado'
            self.stdout.write(self.style.NOTICE(f'{i}. {doc.title}'))
            self.stdout.write(f'   ID: {doc.id}')
            self.stdout.write(f'   Estado: {status}')
            self.stdout.write(f'   Creado: {doc.created_at.strftime("%Y-%m-%d %H:%M")}')
            self.stdout.write(f'   Tamaño: {len(doc.content)} caracteres')

            if verbose and doc.metadata:
                self.stdout.write(f'   Metadata:')
                for key, value in doc.metadata.items():
                    self.stdout.write(f'     - {key}: {value}')

            self.stdout.write('')  # Línea en blanco
