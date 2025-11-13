import os
import logging
from typing import List, Dict, Any, Optional
import chromadb
from sentence_transformers import SentenceTransformer
import ollama
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class RAGService:
    """Servicio principal para el sistema RAG con ChromaDB y Ollama"""
    
    _instance = None
    _chroma_client = None
    _collection = None
    _embedding_model = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RAGService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self.ollama_host = getattr(settings, 'OLLAMA_HOST', 'http://localhost:11434')
        self.collection_name = getattr(settings, 'CHROMA_COLLECTION_NAME', 'videosvoley_docs')
        self.embedding_model = getattr(settings, 'EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
        
        # Inicializar ChromaDB
        self._init_chromadb()
        
        # Inicializar modelo de embeddings
        self._init_embeddings()
        
        # Inicializar Ollama
        self._init_ollama()
        
        self._initialized = True
    
    def _init_chromadb(self):
        """Inicializar ChromaDB"""
        if RAGService._chroma_client is not None:
            self.chroma_client = RAGService._chroma_client
            self.collection = RAGService._collection
            return
            
        try:
            # Configuración de ChromaDB
            persist_dir = getattr(settings, 'CHROMA_PERSIST_DIR', './chroma_db')
            # Asegurar que sea un path absoluto
            if not os.path.isabs(persist_dir):
                persist_dir = os.path.join(settings.BASE_DIR, persist_dir)
            # Normalizar el path para eliminar ./ y //
            persist_dir = os.path.normpath(persist_dir)
            
            RAGService._chroma_client = chromadb.PersistentClient(path=persist_dir)
            self.chroma_client = RAGService._chroma_client
            
            # Obtener o crear colección
            try:
                RAGService._collection = self.chroma_client.get_collection(self.collection_name)
                self.collection = RAGService._collection
                logger.info(f"Colección '{self.collection_name}' encontrada")
            except ValueError:
                # La colección no existe, la creamos
                RAGService._collection = self.chroma_client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Documentos de VideosVoley para RAG"}
                )
                self.collection = RAGService._collection
                logger.info(f"Colección '{self.collection_name}' creada")
            except Exception as e:
                # Si hay otro error, intentamos crear la colección
                logger.warning(f"Error obteniendo colección: {e}. Intentando crear...")
                try:
                    RAGService._collection = self.chroma_client.create_collection(
                        name=self.collection_name,
                        metadata={"description": "Documentos de VideosVoley para RAG"}
                    )
                    self.collection = RAGService._collection
                    logger.info(f"Colección '{self.collection_name}' creada después del error")
                except Exception as create_error:
                    logger.error(f"Error creando colección: {create_error}")
                    raise ImproperlyConfigured(f"Error creando colección ChromaDB: {create_error}")
                
        except Exception as e:
            logger.error(f"Error inicializando ChromaDB: {e}")
            raise ImproperlyConfigured(f"Error configurando ChromaDB: {e}")
    
    def _init_embeddings(self):
        """Inicializar modelo de embeddings"""
        try:
            self.embedding_model_instance = SentenceTransformer(self.embedding_model)
            logger.info(f"Modelo de embeddings '{self.embedding_model}' cargado")
        except Exception as e:
            logger.error(f"Error cargando modelo de embeddings: {e}")
            raise ImproperlyConfigured(f"Error cargando modelo de embeddings: {e}")
    
    def _init_ollama(self):
        """Inicializar conexión con Ollama"""
        try:
            # Configurar client de Ollama con timeouts
            self.ollama_client = ollama.Client(
                host=self.ollama_host,
                timeout=30  # 30 segundos de timeout de conexión
            )
            logger.info(f"Conexión con Ollama configurada en {self.ollama_host} con timeout de 30s")
        except Exception as e:
            logger.error(f"Error configurando Ollama: {e}")
            raise ImproperlyConfigured(f"Error configurando Ollama: {e}")
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generar embedding para un texto"""
        try:
            embedding = self.embedding_model_instance.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            raise
    
    def add_document(self, document_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """Añadir documento a ChromaDB con fragmentación inteligente para PDFs"""
        try:
            # Detectar si es contenido PDF que necesita fragmentación inteligente
            is_pdf_content = (
                metadata.get('content_type', '').lower().find('pdf') != -1 or
                metadata.get('file_ext', '').lower() == '.pdf' or
                metadata.get('topic') == 'volleyball_rules' or
                len(content) > 3000  # Documentos largos que se benefician de fragmentación
            )
            
            if is_pdf_content:
                logger.info(f"Detectado contenido PDF/largo para documento {document_id}, usando fragmentación inteligente")
                return self._add_document_with_smart_chunking(document_id, content, metadata)
            else:
                # Procesamiento normal para documentos cortos
                return self._add_single_document(document_id, content, metadata)
                
        except Exception as e:
            logger.error(f"Error añadiendo documento {document_id}: {e}")
            return False
    
    def _add_single_document(self, document_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """Añade un documento simple sin fragmentación"""
        try:
            # Generar embedding
            embedding = self.generate_embedding(content)
            
            # Limpiar metadatos: ChromaDB no permite valores None
            cleaned_metadata = {k: v for k, v in metadata.items() if v is not None}

            # Añadir a ChromaDB
            self.collection.add(
                ids=[document_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[cleaned_metadata]
            )
            
            logger.info(f"Documento {document_id} añadido a ChromaDB")
            return True
            
        except Exception as e:
            logger.error(f"Error añadiendo documento simple {document_id}: {e}")
            return False
    
    def _add_document_with_smart_chunking(self, document_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """Añade documento usando fragmentación inteligente"""
        try:
            from .pdf_processor import process_pdf_content
            
            # Procesar contenido con fragmentación inteligente
            chunks = process_pdf_content(content)
            
            if not chunks:
                logger.warning(f"No se generaron chunks para documento {document_id}, usando procesamiento simple")
                return self._add_single_document(document_id, content, metadata)
            
            logger.info(f"Generados {len(chunks)} fragmentos inteligentes para documento {document_id}")
            
            # Añadir cada fragmento como un documento separado
            success_count = 0
            for chunk_data in chunks:
                chunk_id = f"{document_id}_{chunk_data['id']}"
                chunk_content = chunk_data['content']
                chunk_metadata = {**metadata, **chunk_data['metadata']}
                
                # Limpiar metadatos
                cleaned_metadata = {k: v for k, v in chunk_metadata.items() if v is not None}
                
                try:
                    # Generar embedding para el fragmento
                    embedding = self.generate_embedding(chunk_content)
                    
                    # Añadir a ChromaDB
                    self.collection.add(
                        ids=[chunk_id],
                        embeddings=[embedding],
                        documents=[chunk_content],
                        metadatas=[cleaned_metadata]
                    )
                    
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Error añadiendo chunk {chunk_id}: {e}")
                    continue
            
            if success_count > 0:
                logger.info(f"Documento {document_id} fragmentado exitosamente: {success_count}/{len(chunks)} fragmentos añadidos")
                return True
            else:
                logger.error(f"No se pudo añadir ningún fragmento del documento {document_id}")
                return False
                
        except ImportError:
            logger.warning("pdf_processor no disponible, usando fragmentación básica")
            return self._add_single_document(document_id, content, metadata)
        except Exception as e:
            logger.error(f"Error en fragmentación inteligente para {document_id}: {e}")
            return False
    
    def search_similar_documents(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Buscar documentos similares a una consulta"""
        try:
            # Mejorar la consulta para categorías específicas
            enhanced_query = self._enhance_query_for_categories(query)
            
            # Generar embedding de la consulta mejorada
            query_embedding = self.generate_embedding(enhanced_query)
            
            # Para consultas generales sobre voleibol, buscar específicamente en documentos manuales
            query_lower = query.lower()
            if any(term in query_lower for term in ['qué es', 'que es', 'definición', 'definicion', 'reglas', 'reglamento', 'altura', 'medidas', 'red']):
                # Buscar solo en documentos de tipo manual (reglamentos)
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results * 3,  # Obtener más resultados
                    where={"source_type": "manual"}  # Filtrar solo documentos manuales
                )
            else:
                # Búsqueda normal para otras consultas
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results * 2  # Obtener más resultados para filtrar
                )
            
            # Formatear y filtrar resultados
            documents = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    documents.append({
                        'content': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else 0.0
                    })
            
            # Filtrar por categoría específica si se menciona en la consulta
            filtered_docs = self._filter_by_category(query, documents)
            
            return filtered_docs[:n_results]
            
        except Exception as e:
            logger.error(f"Error buscando documentos: {e}")
            return []
    
    def _enhance_query_for_categories(self, query: str) -> str:
        """Mejorar la consulta para búsquedas de categorías específicas"""
        query_lower = query.lower()
        
        # Detectar consultas generales sobre voleibol (reglamento, reglas, etc.)
        if any(term in query_lower for term in ['qué es', 'que es', 'definición', 'definicion', 'reglas', 'reglamento', 'altura', 'medidas', 'red', 'cancha', 'campo']):
            return f"{query} reglamento voleibol reglas definición"
        
        # Detectar consultas sobre clasificación/standings
        if any(term in query_lower for term in ['clasificación', 'clasificacion', 'tabla', 'posición', 'posicion', 'puntos']):
            if 'alevín' in query_lower or 'alevin' in query_lower:
                return f"{query} clasificación alevín liga tabla posición"
            elif 'infantil' in query_lower:
                return f"{query} clasificación infantil liga tabla posición"
            elif 'cadete' in query_lower:
                return f"{query} clasificación cadete liga tabla posición"
            else:
                return f"{query} clasificación liga tabla posición"
        
        # Mapear términos de categorías a palabras clave más específicas para partidos
        if 'alevín' in query_lower or 'alevin' in query_lower:
            return f"{query} alevín partido voleibol"
        elif 'infantil' in query_lower:
            return f"{query} infantil partido voleibol"
        elif 'cadete' in query_lower:
            return f"{query} cadete partido voleibol"
        elif 'juvenil' in query_lower:
            return f"{query} juvenil partido voleibol"
        elif 'senior' in query_lower:
            return f"{query} senior partido voleibol"
        
        return query
    
    def _smart_filter_for_rules(self, query_lower: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filtro inteligente para consultas de reglamento usando metadatos enriquecidos"""
        filtered_docs = []
        scored_docs = []
        
        # Detectar tema específico de la consulta
        query_themes = {
            'medidas': ['altura', 'medidas', 'dimensiones', 'metros', 'campo', 'cancha', 'pista', 'red'],
            'reglas': ['reglas', 'reglamento', 'prohibido', 'permitido', 'obligatorio', 'normas'],
            'juego': ['rotación', 'rotacion', 'saque', 'punto', 'set', 'partido', 'toques'],
            'equipos': ['jugadores', 'equipo', 'capitán', 'capitan', 'entrenador'],
            'arbitraje': ['árbitro', 'arbitro', 'falta', 'sanción', 'sancion']
        }
        
        detected_theme = None
        for theme, keywords in query_themes.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_theme = theme
                break
        
        for doc in documents:
            metadata = doc.get('metadata', {})
            score = 0
            
            # Puntuar por metadatos enriquecidos (FASE 6)
            if metadata.get('source_type') == 'manual':
                score += 10  # Base score for manual docs
            
            # Usar metadatos del procesador inteligente
            context_info = metadata.get('context_info', '')
            if detected_theme and f'Tema: {detected_theme}' in context_info:
                score += 20  # Tema específico detectado
            
            if metadata.get('chunk_type') == 'article':
                score += 15  # Artículos específicos son muy relevantes
            elif metadata.get('chunk_type') == 'subsection':
                score += 10  # Subsecciones también relevantes
            
            # Puntuación por contenido de medidas
            if detected_theme == 'medidas' and 'Contiene: medidas' in context_info:
                score += 25  # Muy relevante para consultas de medidas
            
            # Puntuación por reglas específicas
            if 'Tipo: regla específica' in context_info:
                if detected_theme == 'reglas':
                    score += 20
                else:
                    score += 10  # También relevante para otras consultas
            
            # Puntuación por artículo específico mencionado
            article_number = metadata.get('article_number')
            if article_number:
                score += 15
                # Si la consulta menciona un número, priorizar ese artículo
                if article_number in query_lower:
                    score += 30
            
            # Filtrar documentos con score mínimo
            if score >= 10:
                scored_docs.append((doc, score))
        
        # Ordenar por puntuación descendente
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        # Tomar los mejores resultados
        filtered_docs = [doc for doc, score in scored_docs[:5]]
        
        logger.info(f"Filtro inteligente: {len(filtered_docs)} documentos relevantes encontrados para tema '{detected_theme}'")
        return filtered_docs
    
    def _create_enhanced_rules_response(self, query_lower: str, filtered_docs: List[Dict[str, Any]]):
        """Crear respuesta específica y completa para consultas de reglamento"""
        if not filtered_docs:
            return None
            
        # Detectar qué información específica se busca
        seeking_info = {
            'altura': any(term in query_lower for term in ['altura', 'altura de la red', 'red', 'medidas']),
            'rotacion': any(term in query_lower for term in ['rotación', 'rotacion', 'rotar']),
            'toques': any(term in query_lower for term in ['toques', 'toque', 'contactos', 'golpeo']),
            'categorias': any(term in query_lower for term in ['categoría', 'categoria', 'alevín', 'alevin', 'infantil', 'cadete', 'juvenil']),
            'red': any(term in query_lower for term in ['red', 'tocar la red', 'contacto red'])
        }
        
        # Extraer información específica de los documentos
        relevant_info = []
        
        for doc in filtered_docs:
            content = doc['content']
            metadata = doc.get('metadata', {})
            
            # Buscar información específica sobre altura de red
            if seeking_info['altura']:
                height_info = self._extract_height_info(content, metadata)
                if height_info:
                    relevant_info.extend(height_info)
            
            # Buscar información sobre rotación
            if seeking_info['rotacion']:
                rotation_info = self._extract_rotation_info(content, metadata)
                if rotation_info:
                    relevant_info.extend(rotation_info)
            
            # Buscar información sobre toques
            if seeking_info['toques']:
                touches_info = self._extract_touches_info(content, metadata)
                if touches_info:
                    relevant_info.extend(touches_info)
            
            # Buscar información sobre contacto con la red
            if seeking_info['red']:
                net_contact_info = self._extract_net_contact_info(content, metadata)
                if net_contact_info:
                    relevant_info.extend(net_contact_info)
        
        # Crear respuesta estructurada
        if relevant_info:
            response = "📋 <strong>Información del reglamento:</strong>\n\n"
            
            # Remover duplicados manteniendo orden
            seen = set()
            unique_info = []
            for info in relevant_info:
                if info not in seen:
                    seen.add(info)
                    unique_info.append(info)
            
            for info in unique_info[:5]:  # Máximo 5 elementos relevantes
                response += f"• {info}\n\n"
            
            return response.strip()
        
        return None
    
    def _extract_height_info(self, content: str, metadata: Dict) -> List[str]:
        """Extraer información específica sobre altura de red"""
        height_info = []
        content_lower = content.lower()
        
        # Buscar patrones específicos de altura
        import re
        
        # Patrón para alturas con medidas específicas
        height_patterns = [
            r'altura.*?(\d+[,.]?\d*)\s*m.*?(hombres|masculino|masculina)',
            r'altura.*?(\d+[,.]?\d*)\s*m.*?(mujeres|femenino|femenina)',
            r'(\d+[,.]?\d*)\s*m.*?(hombres|masculino)',
            r'(\d+[,.]?\d*)\s*m.*?(mujeres|femenino)',
            r'alevín.*?(\d+[,.]?\d*)\s*m',
            r'infantil.*?(\d+[,.]?\d*)\s*m',
            r'cadete.*?(\d+[,.]?\d*)\s*m',
            r'juvenil.*?(\d+[,.]?\d*)\s*m'
        ]
        
        for pattern in height_patterns:
            matches = re.finditer(pattern, content_lower)
            for match in matches:
                # Extraer contexto alrededor del match
                start = max(0, match.start() - 50)
                end = min(len(content), match.end() + 100)
                context = content[start:end].strip()
                
                if context and len(context) > 10:
                    height_info.append(context)
        
        # Si no encontramos patrones específicos, buscar frases sobre altura
        if not height_info and any(word in content_lower for word in ['altura', 'red']):
            # Buscar en el contenido completo del fragmento, no solo oraciones
            lines = content.split('\n')
            current_context = []
            
            for line in lines:
                line = line.strip()
                current_context.append(line)
                
                # Si encontramos una línea con información de altura
                if any(word in line.lower() for word in ['altura', 'red', 'metros', 'm', '2.', '1.']):
                    # Incluir contexto anterior y posterior
                    context_start = max(0, len(current_context) - 3)
                    context_text = ' '.join(current_context[context_start:])
                    
                    if len(context_text) > 30 and any(word in context_text.lower() for word in ['altura', 'red']):
                        height_info.append(context_text)
                
                # Mantener un buffer de contexto
                if len(current_context) > 5:
                    current_context = current_context[-3:]
            
            # Si aún no tenemos info, buscar por oraciones como fallback
            if not height_info:
                sentences = content.split('.')
                for sentence in sentences:
                    if any(word in sentence.lower() for word in ['altura', 'red', 'metros', 'm']) and len(sentence.strip()) > 20:
                        height_info.append(sentence.strip())
        
        return height_info[:3]  # Máximo 3 resultados
    
    def _extract_rotation_info(self, content: str, metadata: Dict) -> List[str]:
        """Extraer información específica sobre rotación"""
        rotation_info = []
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['rotación', 'rotacion', 'rotar']):
            sentences = content.split('.')
            for sentence in sentences:
                if any(word in sentence.lower() for word in ['rotación', 'rotacion', 'rotar', 'sentido']):
                    clean_sentence = sentence.strip()
                    if len(clean_sentence) > 15:
                        rotation_info.append(clean_sentence)
        
        return rotation_info[:2]
    
    def _extract_touches_info(self, content: str, metadata: Dict) -> List[str]:
        """Extraer información específica sobre toques"""
        touches_info = []
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['toque', 'toques', 'contacto', 'golpeo']):
            sentences = content.split('.')
            for sentence in sentences:
                if any(word in sentence.lower() for word in ['toque', 'toques', 'contacto', 'tres', '3']):
                    clean_sentence = sentence.strip()
                    if len(clean_sentence) > 15:
                        touches_info.append(clean_sentence)
        
        return touches_info[:2]
    
    def _extract_net_contact_info(self, content: str, metadata: Dict) -> List[str]:
        """Extraer información específica sobre contacto con la red"""
        net_info = []
        content_lower = content.lower()
        
        if any(word in content_lower for word in ['red', 'tocar', 'contacto', 'prohibido']):
            sentences = content.split('.')
            for sentence in sentences:
                if any(word in sentence.lower() for word in ['red', 'tocar', 'contacto']):
                    clean_sentence = sentence.strip()
                    if len(clean_sentence) > 15:
                        net_info.append(clean_sentence)
        
        return net_info[:2]
    
    def _filter_by_category(self, original_query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filtrar documentos por categoría específica con metadatos enriquecidos"""
        query_lower = original_query.lower()
        
        # FASE 6 MEJORA: Usar metadatos enriquecidos para filtrado inteligente
        # Para consultas generales sobre voleibol, usar filtrado avanzado
        if any(term in query_lower for term in ['qué es', 'que es', 'definición', 'definicion', 'reglas', 'reglamento', 'altura', 'medidas', 'red', 'rotación', 'rotacion']):
            filtered_docs = self._smart_filter_for_rules(query_lower, documents)
            if filtered_docs:
                return filtered_docs
            
            # Fallback: documentos de tipo manual
            manual_docs = [doc for doc in documents if doc.get('metadata', {}).get('source_type') == 'manual']
            if manual_docs:
                return manual_docs
        
        # Si se menciona una categoría específica, filtrar solo esos documentos
        if 'alevín' in query_lower or 'alevin' in query_lower:
            category_docs = [doc for doc in documents 
                           if 'alevín' in doc['content'].lower()]
            if category_docs:
                return category_docs
        
        elif 'infantil' in query_lower:
            category_docs = [doc for doc in documents 
                           if 'infantil' in doc['content'].lower()]
            if category_docs:
                return category_docs
                
        elif 'cadete' in query_lower:
            category_docs = [doc for doc in documents 
                           if 'cadete' in doc['content'].lower()]
            if category_docs:
                return category_docs
        
        # Si no hay filtro específico o no se encuentran documentos, devolver todos
        return documents
    
    def generate_response(self, query: str, context_documents: List[Dict[str, Any]], 
                         model: str = None) -> str:
        """Generar respuesta usando Ollama con contexto"""
        try:
            # Usar modelo por defecto si no se especifica
            if model is None:
                model = getattr(settings, 'DEFAULT_OLLAMA_MODEL', 'phi3:mini')
            
            # Preparar contexto
            context = "\n\n".join([doc['content'] for doc in context_documents])
            
            # Crear prompt optimizado
            prompt = f"""Eres un asistente especializado en voleibol y el sistema VideosVoley. 
Responde la pregunta del usuario basándote en el contexto proporcionado.

Contexto:
{context}

Pregunta: {query}

Respuesta:"""
            
            # Generar respuesta con Ollama (optimizado para velocidad)
            response = self.ollama_client.generate(
                model=model,
                prompt=prompt,
                options={
                    'temperature': 0.3,      # Más determinista = más rápido
                    'top_p': 0.9,
                    'num_predict': 800,      # Máximo 800 tokens (respuestas más cortas)
                    'timeout': 60            # Timeout específico de 60 segundos
                }
            )
            
            return response['response']
            
        except Exception as e:
            logger.error(f"Error generando respuesta: {e}")
            # Si es un error de memoria o timeout, usar fallback
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["memory", "ram", "system memory", "out of memory", "timeout", "connection", "timed out"]):
                logger.warning(f"Usando fallback por error: {error_str}")
                return self._create_fallback_response(query, context_documents)
            return f"Lo siento, hubo un error generando la respuesta: {str(e)}"
    
    def rag_query(self, query: str, n_results: int = 3, model: str = None) -> Dict[str, Any]:
        """Proceso completo RAG: búsqueda + generación"""
        try:
            # Buscar documentos relevantes
            documents = self.search_similar_documents(query, n_results)
            
            if not documents:
                return {
                    'response': 'No encontré información relevante para tu consulta.',
                    'sources': [],
                    'success': False
                }
            
            # Generar respuesta
            response = self.generate_response(query, documents, model)
            
            return {
                'response': response,
                'sources': documents,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error en consulta RAG: {e}")
            return {
                'response': f'Error procesando la consulta: {str(e)}',
                'sources': [],
                'success': False
            }
    
    def delete_document(self, document_id: str) -> bool:
        """Eliminar documento de ChromaDB"""
        try:
            self.collection.delete(ids=[document_id])
            logger.info(f"Documento {document_id} eliminado de ChromaDB")
            return True
        except Exception as e:
            logger.error(f"Error eliminando documento {document_id}: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas de la colección"""
        try:
            count = self.collection.count()
            return {
                'total_documents': count,
                'collection_name': self.collection_name
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {'total_documents': 0, 'collection_name': self.collection_name}
    
    def _create_fallback_response(self, query: str, context_documents: List[Dict[str, Any]]) -> str:
        """Crear respuesta de respaldo inteligente basada en contexto"""
        if not context_documents:
            return "No encontré información relevante sobre tu consulta. El sistema tuvo un problema técnico, pero puedes intentar reformular la pregunta."
        
        logger.info(f"Usando fallback para consulta: {query[:100]}")
        
        # Analizar la consulta para entender qué busca el usuario
        query_lower = query.lower()
        
        # Detectar tipo de consulta
        is_classification_query = any(term in query_lower for term in ['clasificación', 'clasificacion', 'tabla', 'posición', 'posicion', 'puntos'])
        
        # Filtrar por categoría si se especifica
        filtered_docs = context_documents
        if 'alevín' in query_lower or 'alevin' in query_lower:
            if is_classification_query:
                # Buscar documentos de clasificación de alevín
                filtered_docs = [doc for doc in context_documents 
                               if 'clasificación' in doc['content'].lower() and 'alevín' in doc['content'].lower()]
            else:
                # Buscar documentos relacionados con categorías de alevines
                filtered_docs = [doc for doc in context_documents 
                               if any(keyword in doc['content'].lower() 
                                     for keyword in ['alevín', 'alevin', 'infantil', 'cadete'])]
        elif 'infantil' in query_lower:
            if is_classification_query:
                filtered_docs = [doc for doc in context_documents 
                               if 'clasificación' in doc['content'].lower() and 'infantil' in doc['content'].lower()]
        elif 'cadete' in query_lower:
            if is_classification_query:
                filtered_docs = [doc for doc in context_documents 
                               if 'clasificación' in doc['content'].lower() and 'cadete' in doc['content'].lower()]
        
        if not filtered_docs:
            filtered_docs = context_documents[:3]
        
        # Manejar consultas de clasificación específicamente
        if is_classification_query:
            return self._create_classification_response(query_lower, filtered_docs)
        
        # Extraer información de fechas y partidos
        partidos_info = []
        for doc in filtered_docs[:3]:
            content = doc['content']
            # Extraer información básica del partido
            if 'Fecha:' in content and 'Liga:' in content:
                # Extraer fecha
                try:
                    fecha_start = content.find('Fecha: ') + 7
                    fecha_end = content.find(' |', fecha_start)
                    if fecha_end == -1:
                        fecha_end = content.find('\n', fecha_start)
                    fecha = content[fecha_start:fecha_end].strip()
                    
                    # Extraer equipos
                    partido_start = content.find('Partido: ') + 9
                    partido_end = content.find(' |', partido_start)
                    partido = content[partido_start:partido_end].strip()
                    
                    # Extraer liga/categoría  
                    liga_start = content.find('Liga: ') + 6
                    liga_end = content.find(' |', liga_start)
                    liga = content[liga_start:liga_end].strip()
                    
                    partidos_info.append({
                        'fecha': fecha,
                        'partido': partido,
                        'liga': liga
                    })
                except:
                    continue
        
        # Crear respuesta contextual
        if 'próximo' in query_lower or 'cuando' in query_lower:
            if partidos_info:
                # Filtrar por fechas futuras y ordenar
                try:
                    from datetime import datetime, date
                    
                    def parse_date(fecha_str):
                        try:
                            return datetime.strptime(fecha_str, '%d/%m/%Y').date()
                        except:
                            return date.min
                    
                    # Fecha actual
                    today = date.today()
                    
                    # Filtrar solo partidos futuros
                    future_partidos = []
                    for partido in partidos_info:
                        partido_date = parse_date(partido['fecha'])
                        if partido_date > today:
                            future_partidos.append(partido)
                    
                    if future_partidos:
                        # Ordenar por fecha
                        future_partidos.sort(key=lambda x: parse_date(x['fecha']))
                        
                        if 'alevín' in query_lower:
                            response = f"Los próximos partidos de alevín programados son:\n\n"
                        else:
                            response = f"Los próximos partidos programados son:\n\n"
                        
                        for partido in future_partidos:
                            response += f"📅 **{partido['fecha']}**: {partido['partido']}\n"
                            response += f"   🏆 Liga: {partido['liga']}\n\n"
                        
                        return response.strip()
                    else:
                        # No hay partidos futuros
                        if 'alevín' in query_lower:
                            return "No hay próximos partidos de alevín programados en este momento. Los partidos mostrados ya han pasado."
                        else:
                            return "No hay próximos partidos programados en este momento. Los partidos encontrados ya han pasado."
                except Exception as e:
                    logger.error(f"Error procesando fechas: {e}")
                    pass
        
        # Manejar consultas de información general
        if not is_classification_query and not partidos_info:
            # Intentar extraer información específica sobre medidas de redes
            keywords = ['medidas', 'red', 'altura', 'categorías', 'masculinas', 'femeninas']
            relevant_sentences = []
            for doc in filtered_docs:
                content = doc['content']
                sentences = content.split('.') # Simple split by sentence
                for sentence in sentences:
                    if any(keyword in sentence.lower() for keyword in keywords) and query_lower in sentence.lower():
                        relevant_sentences.append(sentence.strip())
            
            if relevant_sentences:
                response = "Basándome en la información disponible, aquí tienes detalles relevantes:\n\n"
                for sentence in relevant_sentences[:5]: # Limit to 5 relevant sentences
                    response += f"- {sentence}.\n"
                return response.strip()
            
            # FASE 6 MEJORA: Usar extracción inteligente para consultas de reglamento
            enhanced_response = self._create_enhanced_rules_response(query_lower, filtered_docs)
            if enhanced_response:
                return enhanced_response
            
            # Si no se encuentra información específica, proporcionar un resumen más coherente
            response = "Basándome en la información disponible, aquí tienes un resumen de los documentos encontrados:\n\n"
            for i, doc in enumerate(filtered_docs[:3], 1):
                # FASE 6 MEJORA: Mostrar más contenido para reglamentos, especialmente si contiene medidas
                metadata = doc.get('metadata', {})
                if metadata.get('context_info') and 'medidas' in metadata.get('context_info', ''):
                    # Para contenido con medidas, mostrar más texto
                    content_summary = ' '.join(doc['content'].split()[:150]) + "..." if len(doc['content'].split()) > 150 else doc['content']
                else:
                    content_summary = ' '.join(doc['content'].split()[:80]) + "..." if len(doc['content'].split()) > 80 else doc['content']
                response += f"{i}. {content_summary}\n\n"
            
            return response.strip()
        
        # Si no hay filtro específico o no se encuentran documentos, devolver todos
        return filtered_docs
    
    def _create_classification_response(self, query_lower: str, filtered_docs: List[Dict[str, Any]]) -> str:
        """Crear respuesta específica para consultas de clasificación"""
        if not filtered_docs:
            if 'infantil' in query_lower:
                return "No encontré información sobre la clasificación de la liga infantil."
            elif 'alevín' in query_lower:
                return "No encontré información sobre la clasificación de la liga alevín."
            elif 'cadete' in query_lower:
                return "No encontré información sobre la clasificación de la liga cadete."
            else:
                return "No encontré información sobre clasificaciones."
        
        # Extraer información de clasificación
        clasificaciones = []
        for doc in filtered_docs:
            content = doc['content']
            if 'Clasificación Liga:' in content:
                try:
                    # Extraer datos de clasificación
                    parts = content.split(' | ')
                    liga = ""
                    equipo = ""
                    posicion = ""
                    puntos = ""
                    
                    for part in parts:
                        if part.startswith('Clasificación Liga: '):
                            liga = part.replace('Clasificación Liga: ', '')
                        elif part.startswith('Equipo: '):
                            equipo = part.replace('Clasificación Liga: ', '')
                        elif part.startswith('Posición: '):
                            posicion = part.replace('Posición: ', '')
                        elif part.startswith('Puntos totales: '):
                            puntos = part.replace('Puntos totales: ', '')
                    
                    if liga and equipo and posicion:
                        clasificaciones.append({
                            'liga': liga,
                            'equipo': equipo,
                            'posicion': int(posicion) if posicion.isdigit() else 999,
                            'puntos': puntos
                        })
                except:
                    continue
        
        if not clasificaciones:
            return "No pude procesar la información de clasificación encontrada."
        
        # Ordenar por posición
        clasificaciones.sort(key=lambda x: x['posicion'])
        
        # Crear respuesta formateada
        if 'infantil' in query_lower:
            response = "📊 **Clasificación Liga Infantil:**\n\n"
        elif 'alevín' in query_lower:
            response = "📊 **Clasificación Liga Alevín:**\n\n"
        elif 'cadete' in query_lower:
            response = "📊 **Clasificación Liga Cadete:**\n\n"
        else:
            response = "📊 **Clasificación:**\n\n"
        
        for i, cls in enumerate(clasificaciones, 1):
            # Usar emoji según la posición
            if cls['posicion'] == 1:
                emoji = "🥇"
            elif cls['posicion'] == 2:
                emoji = "🥈"
            elif cls['posicion'] == 3:
                emoji = "🥉"
            else:
                emoji = f"{cls['posicion']}."
            
            response += f"{emoji} **{cls['equipo']}** - {cls['puntos']} puntos\n"
        
        return response.strip()
        """Crear respuesta específica para consultas de clasificación"""
        if not filtered_docs:
            if 'infantil' in query_lower:
                return "No encontré información sobre la clasificación de la liga infantil."
            elif 'alevín' in query_lower:
                return "No encontré información sobre la clasificación de la liga alevín."
            elif 'cadete' in query_lower:
                return "No encontré información sobre la clasificación de la liga cadete."
            else:
                return "No encontré información sobre clasificaciones."
        
        # Extraer información de clasificación
        clasificaciones = []
        for doc in filtered_docs:
            content = doc['content']
            if 'Clasificación Liga:' in content:
                try:
                    # Extraer datos de clasificación
                    parts = content.split(' | ')
                    liga = ""
                    equipo = ""
                    posicion = ""
                    puntos = ""
                    
                    for part in parts:
                        if part.startswith('Clasificación Liga: '):
                            liga = part.replace('Clasificación Liga: ', '')
                        elif part.startswith('Equipo: '):
                            equipo = part.replace('Equipo: ', '')
                        elif part.startswith('Posición: '):
                            posicion = part.replace('Posición: ', '')
                        elif part.startswith('Puntos totales: '):
                            puntos = part.replace('Puntos totales: ', '')
                    
                    if liga and equipo and posicion:
                        clasificaciones.append({
                            'liga': liga,
                            'equipo': equipo,
                            'posicion': int(posicion) if posicion.isdigit() else 999,
                            'puntos': puntos
                        })
                except:
                    continue
        
        if not clasificaciones:
            return "No pude procesar la información de clasificación encontrada."
        
        # Ordenar por posición
        clasificaciones.sort(key=lambda x: x['posicion'])
        
        # Crear respuesta formateada
        if 'infantil' in query_lower:
            response = "📊 **Clasificación Liga Infantil:**\n\n"
        elif 'alevín' in query_lower:
            response = "📊 **Clasificación Liga Alevín:**\n\n"
        elif 'cadete' in query_lower:
            response = "📊 **Clasificación Liga Cadete:**\n\n"
        else:
            response = "📊 **Clasificación:**\n\n"
        
        for i, cls in enumerate(clasificaciones, 1):
            # Usar emoji según la posición
            if cls['posicion'] == 1:
                emoji = "🥇"
            elif cls['posicion'] == 2:
                emoji = "🥈"
            elif cls['posicion'] == 3:
                emoji = "🥉"
            else:
                emoji = f"{cls['posicion']}."
            
            response += f"{emoji} **{cls['equipo']}** - {cls['puntos']} puntos\n"
        
        return response.strip()


# Instancia global del servicio (inicializada perezosamente)
_rag_service = None

def get_rag_service():
    """Obtener instancia del servicio RAG (inicialización perezosa)"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service