from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView
from django.db.models import Q
import json
import logging
import time
from django.utils import timezone

from .models import Document, ChatSession, ChatMessage
from .services import get_rag_service
from .query_router import QueryRouter

logger = logging.getLogger(__name__)


@login_required
def rag_chat(request):
    """Vista principal del chat RAG"""
    # Obtener o crear sesión de chat activa
    session, created = ChatSession.objects.get_or_create(
        user=request.user,
        title="Chat RAG",
        defaults={'title': 'Chat RAG'}
    )
    
    # Obtener mensajes de la sesión
    messages_list = ChatMessage.objects.filter(session=session).order_by('created_at')
    
    context = {
        'session': session,
        'messages': messages_list,
        'available_models': ['tinyllama', 'phi3:mini', 'llama3.2', 'llama3.1', 'mistral', 'codellama']
    }
    
    return render(request, 'rag/chat.html', context)


@login_required
@require_http_methods(["POST"])
def send_message(request):
    """Enviar mensaje y obtener respuesta del sistema RAG"""
    try:
        data = json.loads(request.body)
        query = data.get('message', '').strip()
        session_id = data.get('session_id')
        model = data.get('model', 'phi3:mini')
        
        if not query:
            return JsonResponse({'error': 'El mensaje no puede estar vacío'}, status=400)
        
        # Obtener sesión
        session = get_object_or_404(ChatSession, id=session_id, user=request.user)
        
        # Guardar mensaje del usuario
        user_message = ChatMessage.objects.create(
            session=session,
            role='user',
            content=query
        )
        
        # Procesar consulta (con query routing y medición de tiempo)
        start_time = time.time()
        
        # 1. Probar query routing primero
        router = QueryRouter(user=request.user)
        routing_result = router.route_query(query)
        
        response_content = ""
        response_type = "rag_full"
        rag_result = {'sources': []}  # Inicializar para evitar errores
        
        if routing_result['strategy'] == 'direct_query' and routing_result['response']:
            # Respuesta directa sin RAG
            response_content = routing_result['response']
            response_type = 'direct_query'
            rag_result = {'sources': []}  # No hay fuentes en consultas directas
            logger.info(f"Consulta resuelta con query directa: {routing_result['reason']}")
            
        else:
            # Usar RAG (completo o específico)
            rag_service = get_rag_service()
            rag_result = rag_service.rag_query(query, n_results=5, model=model)
            response_content = rag_result['response']
            
            if 'timeout' in response_content.lower() or 'fallback' in str(rag_result.get('sources', [])):
                response_type = 'timeout'
            else:
                response_type = 'rag_success'
        
        response_time = time.time() - start_time
        
        logger.info(f"Consulta procesada en {response_time:.2f}s: '{query[:50]}...' - Tipo: {response_type}")
        
        # Si tardó mucho, loggearlo como warning
        if response_time > 30:
            logger.warning(f"Consulta lenta ({response_time:.2f}s): {query}")
        
        # Guardar respuesta del asistente CON DATOS DE APRENDIZAJE
        assistant_message = ChatMessage.objects.create(
            session=session,
            role='assistant',
            content=response_content,
            response_type=response_type,
            response_time=response_time
        )
        
        # Actualizar título de la sesión si es la primera conversación
        if session.title == "Chat RAG" and ChatMessage.objects.filter(session=session).count() == 2:
            session.title = query[:50] + "..." if len(query) > 50 else query
            session.save()
        
        return JsonResponse({
            'success': True,
            'user_message': {
                'id': user_message.id,
                'content': user_message.content,
                'created_at': user_message.created_at.isoformat()
            },
            'assistant_message': {
                'id': assistant_message.id,
                'content': assistant_message.content,
                'created_at': assistant_message.created_at.isoformat()
            },
            'sources': rag_result.get('sources', [])
        })
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        return JsonResponse({'error': 'Error procesando el mensaje'}, status=500)


@login_required
def chat_sessions(request):
    """Lista de sesiones de chat del usuario"""
    sessions = ChatSession.objects.filter(user=request.user).order_by('-updated_at')
    return render(request, 'rag/sessions.html', {'sessions': sessions})


@login_required
def chat_session_detail(request, session_id):
    """Detalle de una sesión de chat específica"""
    session = get_object_or_404(ChatSession, id=session_id, user=request.user)
    messages_list = ChatMessage.objects.filter(session=session).order_by('created_at')
    
    context = {
        'session': session,
        'messages': messages_list,
        'available_models': ['tinyllama', 'phi3:mini', 'llama3.2', 'llama3.1', 'mistral', 'codellama']
    }
    
    return render(request, 'rag/chat.html', context)


@login_required
def create_new_session(request):
    """Crear nueva sesión de chat"""
    session = ChatSession.objects.create(
        user=request.user,
        title="Nueva conversación"
    )
    return redirect('rag:chat_session_detail', session_id=session.id)


@login_required
def delete_session(request, session_id):
    """Eliminar sesión de chat"""
    session = get_object_or_404(ChatSession, id=session_id, user=request.user)
    session.delete()
    messages.success(request, 'Sesión eliminada correctamente')
    return redirect('rag:chat_sessions')


@login_required
def documents_list(request):
    """Lista de documentos indexados"""
    documents = Document.objects.all().order_by('-created_at')
    
    # Filtros
    search = request.GET.get('search', '')
    source_type = request.GET.get('source_type', '')
    is_indexed = request.GET.get('is_indexed', '')
    
    if search:
        documents = documents.filter(
            Q(title__icontains=search) | Q(content__icontains=search)
        )
    
    if source_type:
        documents = documents.filter(source_type=source_type)
    
    if is_indexed:
        documents = documents.filter(is_indexed=is_indexed == 'true')
    
    context = {
        'documents': documents,
        'search': search,
        'source_type': source_type,
        'is_indexed': is_indexed,
        'source_type_choices': Document._meta.get_field('source_type').choices
    }
    
    return render(request, 'rag/documents.html', context)


@login_required
def document_detail(request, document_id):
    """Detalle de un documento"""
    document = get_object_or_404(Document, id=document_id)
    return render(request, 'rag/document_detail.html', {'document': document})


@login_required
@require_http_methods(["POST"])
def reindex_document(request, document_id):
    """Reindexar un documento específico"""
    document = get_object_or_404(Document, id=document_id)
    
    try:
        rag_service = get_rag_service()
        # Eliminar de ChromaDB si existe
        rag_service.delete_document(str(document.id))
        
        # Reindexar
        success = rag_service.add_document(
            document_id=str(document.id),
            content=document.content,
            metadata={
                'title': document.title,
                'source_type': document.source_type,
                'source_id': document.source_id,
                'created_at': document.created_at.isoformat(),
                **document.metadata
            }
        )
        
        if success:
            document.is_indexed = True
            document.save()
            messages.success(request, 'Documento reindexado correctamente')
        else:
            messages.error(request, 'Error reindexando el documento')
            
    except Exception as e:
        logger.error(f"Error reindexando documento {document_id}: {e}")
        messages.error(request, f'Error reindexando el documento: {str(e)}')
    
    return redirect('rag:document_detail', document_id=document.id)


@login_required
def rag_stats(request):
    """Estadísticas del sistema RAG"""
    try:
        rag_service = get_rag_service()
        chroma_stats = rag_service.get_collection_stats()
    
        context = {
            'chroma_stats': chroma_stats,
            'total_documents': Document.objects.count(),
            'indexed_documents': Document.objects.filter(is_indexed=True).count(),
            'total_sessions': ChatSession.objects.filter(user=request.user).count(),
            'total_messages': ChatMessage.objects.filter(session__user=request.user).count()
        }
        
        return render(request, 'rag/stats.html', context)
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        messages.error(request, f'Error obteniendo estadísticas: {str(e)}')
        return redirect('rag:rag_chat')


@login_required
@require_http_methods(["POST"])
def rate_message(request):
    """Valorar mensaje del asistente"""
    try:
        data = json.loads(request.body)
        message_id = data.get('message_id')
        rating = data.get('rating')
        
        if not message_id or rating not in [1, 2]:
            return JsonResponse({'error': 'Datos inválidos'}, status=400)
        
        # Verificar que el mensaje pertenece a una sesión del usuario
        message = get_object_or_404(
            ChatMessage, 
            id=message_id,
            session__user=request.user,
            role='assistant'  # Solo se pueden valorar respuestas del asistente
        )
        
        # Actualizar rating
        message.user_rating = rating
        message.save()
        
        logger.info(f"Usuario {request.user.username} valoró mensaje {message_id} con {rating}")
        
        return JsonResponse({
            'success': True,
            'message': 'Valoración guardada correctamente'
        })
        
    except Exception as e:
        logger.error(f"Error valorando mensaje: {e}")
        return JsonResponse({'error': 'Error guardando la valoración'}, status=500)