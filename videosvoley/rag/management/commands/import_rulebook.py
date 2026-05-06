from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.conf import settings
from videosvoley.rag.models import Document
from videosvoley.rag.services import get_rag_service

import logging
import os

logger = logging.getLogger(__name__)

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

# PDF parsing is optional
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


class Command(BaseCommand):
    help = 'Importar y indexar un reglamento de voleibol como documento manual en el sistema RAG'

    def add_arguments(self, parser):
        parser.add_argument('--url', type=str, help='URL del documento (HTML o PDF)')
        parser.add_argument('--file', type=str, help='Ruta local del archivo (txt, md, html o pdf)')
        parser.add_argument('--title', type=str, default='Reglamento de Voleibol', help='Título del documento')
        parser.add_argument('--force-reindex', action='store_true', help='Forzar reindexación si ya existe')
        parser.add_argument('--dry-run', action='store_true', help='Mostrar acciones sin realizar cambios')
        parser.add_argument('--verbose', action='store_true', help='Mostrar información detallada del proceso')

    def handle(self, *args, **options):
        source_url = options.get('url')
        file_path = options.get('file')
        title = options['title']
        force_reindex = options['force_reindex']
        dry_run = options['dry_run']
        verbose = options.get('verbose', False)

        if not source_url and not file_path:
            # Intentar desde settings si existe
            source_url = getattr(settings, 'RAG_RULEBOOK_URL', None)
            if not source_url:
                raise CommandError('Debes proporcionar --url o --file, o configurar RAG_RULEBOOK_URL en settings')

        # Obtener contenido
        if verbose:
            self.stdout.write(self.style.NOTICE(f'📄 Cargando contenido desde: {source_url or file_path}'))

        content, metadata_extra = self._load_content(source_url, file_path)

        if verbose:
            self.stdout.write(self.style.NOTICE(f'✅ Contenido cargado: {len(content)} caracteres'))
            self.stdout.write(self.style.NOTICE(f'📊 Metadata: {metadata_extra}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY RUN - No se realizarán cambios'))
            preview = (content[:200] + '...') if content and len(content) > 200 else (content or 'SIN CONTENIDO')
            self.stdout.write(f'- Título: {title}')
            self.stdout.write(f'- Origen: {source_url or file_path}')
            self.stdout.write(f'- Contenido (preview):\n{preview}')
            return

        # Crear o actualizar documento en BD
        doc, created = Document.objects.get_or_create(
            source_type='manual',
            source_id=None,
            title=title,
            defaults={
                'content': content or 'Contenido no extraído.',
                'metadata': {
                    'topic': 'volleyball_rules',
                    'source_url': source_url,
                    'file_path': file_path,
                    **metadata_extra,
                },
                'is_indexed': False,
            }
        )

        if not created:
            doc.content = content or doc.content
            # mezclar metadatos
            meta = doc.metadata or {}
            meta.update({'topic': 'volleyball_rules', 'source_url': source_url, 'file_path': file_path})
            meta.update(metadata_extra)
            doc.metadata = meta
            if force_reindex:
                doc.is_indexed = False
            doc.save()

        # Indexar en Chroma
        if verbose:
            self.stdout.write(self.style.NOTICE(f'🔄 Indexando en ChromaDB con ID: {doc.id}'))
            self.stdout.write(self.style.NOTICE(f'📝 Usando fragmentación inteligente: {self._will_use_smart_chunking(doc.metadata)}'))

        rag_service = get_rag_service()
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
            self.stdout.write(self.style.SUCCESS(f"✅ Documento '{doc.title}' importado e indexado (ID {doc.id})"))
            if verbose:
                self.stdout.write(self.style.SUCCESS(f'💾 Documento marcado como indexado en BD'))
        else:
            self.stdout.write(self.style.ERROR('❌ Error indexando el documento en ChromaDB'))

    def _will_use_smart_chunking(self, metadata: dict) -> bool:
        """Verifica si el documento usará fragmentación inteligente basado en metadata"""
        return (
            metadata.get('content_type', '').lower().find('pdf') != -1 or
            metadata.get('file_ext', '').lower() == '.pdf' or
            metadata.get('topic') == 'volleyball_rules'
        )

    def _load_content(self, url: str | None, file_path: str | None):
        metadata_extra = {}
        text = None

        if url:
            if not requests:
                raise CommandError('La librería requests no está disponible en el entorno')
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                content_type = resp.headers.get('Content-Type', '')
                metadata_extra['content_type'] = content_type

                if 'pdf' in content_type.lower() or (url.lower().endswith('.pdf')):
                    if not PdfReader:
                        self.stdout.write(self.style.WARNING('PyPDF2 no disponible, guardando referencia sin extraer texto'))
                        text = f"Documento PDF (no extraído). Consulta el original: {url}"
                    else:
                        text = self._extract_pdf_bytes(resp.content)
                else:
                    # HTML o texto
                    text = self._extract_html_text(resp.text)
            except Exception as e:
                logger.error(f'Error descargando URL {url}: {e}')
                raise CommandError(f'No se pudo descargar el documento desde la URL: {e}')

        elif file_path:
            if not os.path.exists(file_path):
                raise CommandError(f'Archivo no encontrado: {file_path}')
            ext = os.path.splitext(file_path)[1].lower()
            metadata_extra['file_ext'] = ext
            try:
                if ext in ['.txt', '.md']:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                elif ext in ['.html', '.htm']:
                    if not BeautifulSoup:
                        raise CommandError('bs4 no disponible para parsear HTML')
                    with open(file_path, 'r', encoding='utf-8') as f:
                        html = f.read()
                        text = self._extract_html_text(html)
                elif ext == '.pdf':
                    if not PdfReader:
                        raise CommandError('PyPDF2 no disponible para leer PDFs')
                    with open(file_path, 'rb') as f:
                        text = self._extract_pdf_file(f)
                else:
                    raise CommandError('Formato de archivo no soportado. Use txt, md, html o pdf')
            except Exception as e:
                logger.error(f'Error leyendo archivo {file_path}: {e}')
                raise CommandError(f'No se pudo leer el archivo: {e}')

        return text, metadata_extra

    def _extract_html_text(self, html: str) -> str:
        if not BeautifulSoup:
            return html
        soup = BeautifulSoup(html, 'html.parser')
        # Eliminar scripts y estilos
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        return text

    def _extract_pdf_file(self, file_obj) -> str:
        try:
            reader = PdfReader(file_obj)
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or '')
            return '\n'.join(pages)
        except Exception as e:
            logger.error(f'Error extrayendo texto de PDF: {e}')
            return 'Contenido PDF no pudo ser extraído.'

    def _extract_pdf_bytes(self, data: bytes) -> str:
        import io
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or '')
            return '\n'.join(pages)
        except Exception as e:
            logger.error(f'Error extrayendo texto de PDF descargado: {e}')
            return 'Contenido PDF no pudo ser extraído.'
