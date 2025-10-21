# Sistema RAG para VideosVoley

Este módulo implementa un sistema de Retrieval-Augmented Generation (RAG) que permite hacer consultas inteligentes sobre el contenido de VideosVoley usando ChromaDB y Ollama.

## Características

- **Búsqueda semántica**: Encuentra información relevante usando embeddings
- **Generación de respuestas**: Usa Ollama para generar respuestas contextuales
- **Indexación automática**: Indexa videos, imágenes, partidos y ligas automáticamente
- **Interfaz de chat**: Chat interactivo para hacer consultas
- **Historial de conversaciones**: Guarda el historial de chat por usuario
- **Múltiples modelos**: Soporte para diferentes modelos de Ollama

## Configuración

### Opción 1: Ollama Externo (Recomendado)

Si ya tienes Ollama configurado por separado (con OpenWebUI, etc.):

```bash
# Ejecutar script de configuración
./setup_rag_external_ollama.sh
```

### Opción 2: Ollama en Docker

Si prefieres tener Ollama en Docker:

```bash
# Ejecutar script de configuración
./setup_rag.sh
```

### Variables de Entorno

```bash
# Ollama (externo o local)
OLLAMA_HOST=http://tu-servidor:11434

# ChromaDB
CHROMA_COLLECTION_NAME=videosvoley_docs
CHROMA_PERSIST_DIR=./chroma_db

# Modelo de embeddings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Modelo por defecto (phi3:mini recomendado)
DEFAULT_OLLAMA_MODEL=phi3:mini
```

## Uso

### 1. Iniciar el sistema

```bash
# Desarrollo
docker-compose -f docker-compose.dev.yml up

# Producción
docker-compose up
```

### 2. Configurar Ollama

**Con Ollama externo (recomendado):**
```bash
# El script detectará automáticamente tu servidor Ollama
./setup_rag_external_ollama.sh
```

**Con Ollama en Docker:**
```bash
# Instalar modelos
docker-compose exec ollama ollama pull phi3:mini
docker-compose exec ollama ollama pull llama3.2
docker-compose exec ollama ollama pull llama3.1
docker-compose exec ollama ollama pull mistral
```

### 3. Indexar documentos

```bash
# Indexar todos los documentos
docker-compose exec web python manage.py index_documents

# Indexar solo videos
docker-compose exec web python manage.py index_documents --source-type video

# Indexar con límite
docker-compose exec web python manage.py index_documents --limit 100

# Forzar reindexación
docker-compose exec web python manage.py index_documents --force

# Modo dry-run (ver qué se indexaría)
docker-compose exec web python manage.py index_documents --dry-run
```

### 4. Limpiar datos RAG

```bash
# Limpiar todo (requiere confirmación)
docker-compose exec web python manage.py clear_rag_data --confirm

# Mantener conversaciones
docker-compose exec web python manage.py clear_rag_data --confirm --keep-chat

# Mantener documentos en BD
docker-compose exec web python manage.py clear_rag_data --confirm --keep-documents
```

## Interfaz Web

### URLs Disponibles

- `/rag/` - Chat principal
- `/rag/chat/sessions/` - Lista de conversaciones
- `/rag/documents/` - Lista de documentos indexados
- `/rag/stats/` - Estadísticas del sistema

### Funcionalidades del Chat

1. **Selección de modelo**: Cambiar entre diferentes modelos de Ollama
2. **Búsqueda contextual**: El sistema busca información relevante antes de responder
3. **Fuentes consultadas**: Muestra qué documentos se usaron para la respuesta
4. **Historial**: Guarda todas las conversaciones por usuario
5. **Nuevas conversaciones**: Crear múltiples hilos de conversación

## Arquitectura

### Componentes

1. **RAGService**: Servicio principal que maneja ChromaDB y Ollama
2. **Document Model**: Almacena documentos indexados en la BD
3. **ChatSession/ChatMessage**: Gestiona conversaciones de chat
4. **Management Commands**: Comandos para indexar y gestionar datos

### Flujo de Trabajo

1. **Indexación**: Los documentos se procesan y se almacenan en ChromaDB
2. **Consulta**: El usuario hace una pregunta
3. **Búsqueda**: Se buscan documentos relevantes usando embeddings
4. **Generación**: Ollama genera una respuesta usando el contexto encontrado
5. **Respuesta**: Se devuelve la respuesta con las fuentes consultadas

### Modelos de Datos

#### Document
- `title`: Título del documento
- `content`: Contenido para indexar
- `source_type`: Tipo (video, image, match, league)
- `source_id`: ID del objeto original
- `metadata`: Metadatos adicionales
- `is_indexed`: Estado de indexación

#### ChatSession
- `user`: Usuario propietario
- `title`: Título de la conversación
- `created_at/updated_at`: Timestamps

#### ChatMessage
- `session`: Sesión a la que pertenece
- `role`: user o assistant
- `content`: Contenido del mensaje
- `created_at`: Timestamp

## Personalización

### Añadir Nuevos Tipos de Documentos

1. Crear método en `RAGService` para el nuevo tipo
2. Añadir comando de indexación en `index_documents.py`
3. Actualizar el modelo `Document` si es necesario

### Cambiar Modelo de Embeddings

```python
# En settings.py
EMBEDDING_MODEL = 'sentence-transformers/otro-modelo'
```

### Configurar Ollama

```python
# En settings.py
OLLAMA_HOST = 'http://tu-servidor-ollama:11434'
```

## Monitoreo

### Logs

Los logs del sistema RAG se pueden encontrar en:
- Django logs: `rag` logger
- ChromaDB: Logs internos
- Ollama: Logs del contenedor

### Estadísticas

La página `/rag/stats/` muestra:
- Documentos en ChromaDB
- Documentos indexados
- Conversaciones del usuario
- Estado del sistema

## Troubleshooting

### Ollama no responde

```bash
# Verificar estado
docker-compose ps ollama

# Ver logs
docker-compose logs ollama

# Reiniciar
docker-compose restart ollama
```

### ChromaDB no funciona

```bash
# Verificar permisos del directorio
ls -la ./chroma_db

# Limpiar y recrear
rm -rf ./chroma_db
docker-compose exec web python manage.py index_documents
```

### Modelos no cargan

```bash
# Verificar modelos disponibles
docker-compose exec ollama ollama list

# Instalar modelo específico
docker-compose exec ollama ollama pull llama3.2
```

## Desarrollo

### Añadir Nuevas Funcionalidades

1. Crear vistas en `views.py`
2. Añadir URLs en `urls.py`
3. Crear templates en `templates/rag/`
4. Actualizar `RAGService` si es necesario

### Testing

```bash
# Ejecutar tests
docker-compose exec web python manage.py test rag
```

### Debugging

```python
# En el shell de Django
from videosvoley.rag.services import rag_service

# Verificar conexión
rag_service.get_collection_stats()

# Probar búsqueda
results = rag_service.search_similar_documents("tu consulta")
print(results)
```