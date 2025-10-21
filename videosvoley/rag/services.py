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
            # Configurar client de Ollama
            self.ollama_client = ollama.Client(host=self.ollama_host)
            logger.info(f"Conexión con Ollama configurada en {self.ollama_host}")
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
        """Añadir documento a ChromaDB"""
        try:
            # Generar embedding
            embedding = self.generate_embedding(content)
            
            # Añadir a ChromaDB
            self.collection.add(
                ids=[document_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            
            logger.info(f"Documento {document_id} añadido a ChromaDB")
            return True
            
        except Exception as e:
            logger.error(f"Error añadiendo documento {document_id}: {e}")
            return False
    
    def search_similar_documents(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Buscar documentos similares a una consulta"""
        try:
            # Mejorar la consulta para categorías específicas
            enhanced_query = self._enhance_query_for_categories(query)
            
            # Generar embedding de la consulta mejorada
            query_embedding = self.generate_embedding(enhanced_query)
            
            # Buscar en ChromaDB
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
    
    def _filter_by_category(self, original_query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filtrar documentos por categoría específica mencionada en la consulta"""
        query_lower = original_query.lower()
        
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
            
            # Crear prompt optimizado para phi3:mini
            prompt = f"""Eres un asistente especializado en voleibol y el sistema VideosVoley. 
Responde la pregunta del usuario basándote en el contexto proporcionado.

Contexto:
{context}

Pregunta: {query}

Respuesta:"""
            
            # Generar respuesta con Ollama (con timeout thread-safe)
            import threading
            import time
            
            response_container = {'response': None, 'error': None}
            
            def ollama_request():
                try:
                    response_container['response'] = self.ollama_client.generate(
                        model=model,
                        prompt=prompt,
                        options={
                            'temperature': 0.7,
                            'top_p': 0.9,
                            'max_tokens': 1000
                        }
                    )
                except Exception as e:
                    response_container['error'] = e
            
            # Ejecutar request en un hilo separado con timeout
            thread = threading.Thread(target=ollama_request)
            thread.daemon = True
            thread.start()
            thread.join(timeout=30)  # 30 second timeout
            
            if thread.is_alive():
                # Request timed out, provide fallback response
                return self._create_fallback_response(query, context_documents)
            
            if response_container['error']:
                # If it's a connection-related error, provide context summary
                error_str = str(response_container['error']).lower()
                if "connection" in error_str or "refused" in error_str or "timeout" in error_str:
                    return self._create_fallback_response(query, context_documents)
                else:
                    raise response_container['error']
            
            if response_container['response']:
                response = response_container['response']
            
            return response['response']
            
        except Exception as e:
            logger.error(f"Error generando respuesta: {e}")
            return f"Lo siento, hubo un error generando la respuesta: {str(e)}"
    
    def rag_query(self, query: str, n_results: int = 5, model: str = None) -> Dict[str, Any]:
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
            return "No encontré información relevante sobre tu consulta."
        
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
        
        # Respuesta genérica mejorada
        response = "Basándome en la información disponible:\n\n"
        for i, doc in enumerate(filtered_docs[:3], 1):
            content_preview = doc['content'][:150] + "..." if len(doc['content']) > 150 else doc['content']
            response += f"{i}. {content_preview}\n\n"
        
        return response.strip()
    
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