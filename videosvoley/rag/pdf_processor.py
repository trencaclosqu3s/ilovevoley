"""
PDF Processor inteligente para fragmentación semántica
Resuelve el problema de fragmentación básica del RAG actual
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DocumentChunk:
    """Fragmento de documento con contexto preservado"""
    content: str
    section_title: str
    subsection_title: Optional[str] = None
    article_number: Optional[str] = None
    chunk_type: str = 'content'  # 'title', 'article', 'content', 'list'
    page_number: Optional[int] = None
    context_info: str = ''
    
    def get_searchable_content(self) -> str:
        """Obtiene contenido enriquecido para búsqueda"""
        parts = []
        
        if self.section_title:
            parts.append(f"Sección: {self.section_title}")
        
        if self.subsection_title:
            parts.append(f"Subsección: {self.subsection_title}")
            
        if self.article_number:
            parts.append(f"Artículo {self.article_number}")
            
        if self.context_info:
            parts.append(self.context_info)
            
        parts.append(self.content)
        
        return " | ".join(parts)


class SmartPDFProcessor:
    """Procesador inteligente de PDFs para deportes"""
    
    def __init__(self):
        # Patrones para detectar estructura en documentos deportivos
        self.title_patterns = [
            r'^ARTÍCULO\s+(\d+)[.:]\s*(.+)',
            r'^ART[ÍI]CULO\s+(\d+)[.:]\s*(.+)',
            r'^(\d+)[.:]\s*([A-ZÁÉÍÓÚÑÜ][^.]{10,})',
            r'^CAPÍTULO\s+(\d+)[.:]\s*(.+)',
            r'^CAP[ÍI]TULO\s+(\d+)[.:]\s*(.+)',
            r'^SECCIÓN\s+(\d+)[.:]\s*(.+)',
            r'^SECCI[ÓO]N\s+(\d+)[.:]\s*(.+)',
            r'^(\d+\.\d+)[.:]\s*(.+)',  # 1.1, 2.3, etc.
            r'^([IVX]+)[.:]\s*([A-ZÁÉÍÓÚÑÜ].+)',  # Números romanos
        ]
        
        self.subtitle_patterns = [
            r'^([a-z])\)\s*(.+)',  # a), b), c)
            r'^(\d+\.\d+\.\d+)[.:]\s*(.+)',  # 1.1.1
            r'^\-\s*(.+)',  # Listas con guión
            r'^\•\s*(.+)',  # Listas con bullet
            r'^\*\s*(.+)',  # Listas con asterisco
        ]
        
        # Palabras clave para contexto deportivo
        self.sports_keywords = {
            'medidas': ['campo', 'cancha', 'pista', 'terreno', 'dimensiones', 'metros', 'líneas'],
            'reglas': ['reglamento', 'normas', 'prohibido', 'permitido', 'obligatorio'],
            'juego': ['partido', 'encuentro', 'juego', 'set', 'punto', 'tanto'],
            'equipos': ['equipo', 'jugadores', 'entrenador', 'capitán'],
            'arbitraje': ['árbitro', 'juez', 'falta', 'sanción', 'tarjeta'],
            'competición': ['torneo', 'campeonato', 'liga', 'clasificación']
        }
    
    def process_pdf_content(self, raw_content: str) -> List[DocumentChunk]:
        """Procesa contenido de PDF y devuelve fragmentos inteligentes"""
        logger.info("Iniciando procesamiento inteligente de PDF")
        
        # 1. Limpiar y normalizar texto
        cleaned_content = self._clean_text(raw_content)
        
        # 2. Detectar estructura jerárquica
        structured_content = self._detect_structure(cleaned_content)
        
        # 3. Crear fragmentos inteligentes
        chunks = self._create_smart_chunks(structured_content)
        
        logger.info(f"PDF procesado: {len(chunks)} fragmentos inteligentes creados")
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Limpia y normaliza el texto del PDF"""
        # Eliminar caracteres de control y normalizar espacios
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Normalizar saltos de línea
        text = re.sub(r'\r\n|\r', '\n', text)
        
        # Eliminar líneas vacías múltiples
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Normalizar espacios múltiples
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Unir líneas partidas por fin de línea (típico en PDFs)
        text = re.sub(r'([a-z])\-\n([a-z])', r'\1\2', text)
        text = re.sub(r'([a-záéíóúñü])\n([a-záéíóúñü])', r'\1 \2', text)
        
        return text.strip()
    
    def _detect_structure(self, text: str) -> List[Dict]:
        """Detecta la estructura jerárquica del documento"""
        lines = text.split('\n')
        structured_elements = []
        current_section = None
        current_subsection = None
        current_article = None
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Detectar títulos principales (Artículos, Capítulos)
            title_match = self._match_title_patterns(line)
            if title_match:
                article_num, title = title_match
                current_article = article_num
                current_section = title
                current_subsection = None
                
                structured_elements.append({
                    'type': 'article',
                    'content': line,
                    'article_number': article_num,
                    'section_title': title,
                    'line_number': line_num
                })
                continue
            
            # Detectar subtítulos
            subtitle_match = self._match_subtitle_patterns(line)
            if subtitle_match:
                sub_num, subtitle = subtitle_match
                current_subsection = subtitle
                
                structured_elements.append({
                    'type': 'subsection',
                    'content': line,
                    'subsection_title': subtitle,
                    'section_title': current_section,
                    'article_number': current_article,
                    'line_number': line_num
                })
                continue
            
            # Detectar listas
            if self._is_list_item(line):
                structured_elements.append({
                    'type': 'list_item',
                    'content': line,
                    'section_title': current_section,
                    'subsection_title': current_subsection,
                    'article_number': current_article,
                    'line_number': line_num
                })
                continue
            
            # Contenido regular
            if len(line) > 20:  # Filtrar líneas muy cortas
                structured_elements.append({
                    'type': 'content',
                    'content': line,
                    'section_title': current_section,
                    'subsection_title': current_subsection,
                    'article_number': current_article,
                    'line_number': line_num
                })
        
        return structured_elements
    
    def _match_title_patterns(self, line: str) -> Optional[Tuple[str, str]]:
        """Detecta si la línea es un título principal"""
        for pattern in self.title_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                if len(match.groups()) >= 2:
                    return match.group(1), match.group(2).strip()
                else:
                    return match.group(1), line.strip()
        return None
    
    def _match_subtitle_patterns(self, line: str) -> Optional[Tuple[str, str]]:
        """Detecta si la línea es un subtítulo"""
        for pattern in self.subtitle_patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                if len(match.groups()) >= 2:
                    return match.group(1), match.group(2).strip()
                else:
                    return match.group(1), line.strip()
        return None
    
    def _is_list_item(self, line: str) -> bool:
        """Detecta si la línea es un elemento de lista"""
        list_patterns = [
            r'^\-\s+.+',
            r'^\•\s+.+',
            r'^\*\s+.+',
            r'^[a-z]\)\s+.+',
            r'^\d+\)\s+.+',
        ]
        
        return any(re.match(pattern, line) for pattern in list_patterns)
    
    def _create_smart_chunks(self, structured_elements: List[Dict]) -> List[DocumentChunk]:
        """Crea fragmentos inteligentes preservando contexto"""
        chunks = []
        current_chunk_content = []
        current_context = {}
        
        for element in structured_elements:
            # Actualizar contexto actual
            if element.get('section_title'):
                current_context['section_title'] = element['section_title']
            if element.get('subsection_title'):
                current_context['subsection_title'] = element['subsection_title']
            if element.get('article_number'):
                current_context['article_number'] = element['article_number']
            
            # Si es un nuevo artículo/sección, finalizar chunk anterior
            if element['type'] in ['article', 'subsection'] and current_chunk_content:
                chunk = self._finalize_chunk(current_chunk_content, current_context)
                if chunk:
                    chunks.append(chunk)
                current_chunk_content = []
            
            # Añadir contenido al chunk actual
            current_chunk_content.append(element)
            
            # Si el chunk es muy largo, fragmentarlo
            total_length = sum(len(el['content']) for el in current_chunk_content)
            if total_length > 1500:  # Límite de caracteres por chunk
                chunk = self._finalize_chunk(current_chunk_content, current_context)
                if chunk:
                    chunks.append(chunk)
                current_chunk_content = []
        
        # Procesar último chunk
        if current_chunk_content:
            chunk = self._finalize_chunk(current_chunk_content, current_context)
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def _finalize_chunk(self, elements: List[Dict], context: Dict) -> Optional[DocumentChunk]:
        """Finaliza y crea un DocumentChunk"""
        if not elements:
            return None
        
        # Combinar contenido preservando estructura
        content_parts = []
        chunk_type = 'content'
        
        for element in elements:
            if element['type'] == 'article':
                content_parts.append(f"ARTÍCULO {element.get('article_number', '')}: {element['content']}")
                chunk_type = 'article'
            elif element['type'] == 'subsection':
                content_parts.append(f"SUBSECCIÓN: {element['content']}")
                chunk_type = 'subsection'
            elif element['type'] == 'list_item':
                content_parts.append(f"• {element['content']}")
                chunk_type = 'list'
            else:
                content_parts.append(element['content'])
        
        content = '\n'.join(content_parts)
        
        # Enriquecer con contexto deportivo
        context_info = self._generate_context_info(content, context)
        
        return DocumentChunk(
            content=content,
            section_title=context.get('section_title', ''),
            subsection_title=context.get('subsection_title'),
            article_number=context.get('article_number'),
            chunk_type=chunk_type,
            context_info=context_info
        )
    
    def _generate_context_info(self, content: str, context: Dict) -> str:
        """Genera información de contexto para mejorar búsquedas"""
        context_parts = []
        content_lower = content.lower()
        
        # Detectar temas deportivos
        for theme, keywords in self.sports_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                context_parts.append(f"Tema: {theme}")
                break
        
        # Detectar si son reglas específicas
        if any(word in content_lower for word in ['prohibido', 'obligatorio', 'debe', 'deberá', 'no puede']):
            context_parts.append("Tipo: regla específica")
        
        # Detectar medidas y dimensiones
        if re.search(r'\d+[\.\,]?\d*\s*(metro|cm|mm|m\b)', content_lower):
            context_parts.append("Contiene: medidas")
        
        return " | ".join(context_parts)
    
    def process_for_rag(self, raw_content: str) -> List[Dict[str, str]]:
        """Interfaz compatible con RAG actual"""
        chunks = self.process_pdf_content(raw_content)
        
        # Convertir a formato esperado por RAG
        rag_documents = []
        for i, chunk in enumerate(chunks):
            rag_documents.append({
                'id': f"chunk_{i}",
                'content': chunk.get_searchable_content(),
                'metadata': {
                    'section_title': chunk.section_title,
                    'subsection_title': chunk.subsection_title,
                    'article_number': chunk.article_number,
                    'chunk_type': chunk.chunk_type,
                    'context_info': chunk.context_info,
                }
            })
        
        return rag_documents


# Función de conveniencia para usar desde otros módulos
def process_pdf_content(raw_content: str) -> List[Dict[str, str]]:
    """Función de conveniencia para procesar PDFs"""
    processor = SmartPDFProcessor()
    return processor.process_for_rag(raw_content)