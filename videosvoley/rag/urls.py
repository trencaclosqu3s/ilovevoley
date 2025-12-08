from django.urls import path
from . import views

app_name = 'rag'

urlpatterns = [
    # Chat RAG
    path('', views.rag_chat, name='rag_chat'),
    path('chat/', views.rag_chat, name='rag_chat'),
    path('chat/sessions/', views.chat_sessions, name='chat_sessions'),
    path('chat/sessions/new/', views.create_new_session, name='create_new_session'),
    path('chat/sessions/<int:session_id>/', views.chat_session_detail, name='chat_session_detail'),
    path('chat/sessions/<int:session_id>/delete/', views.delete_session, name='delete_session'),
    path('chat/send-message/', views.send_message, name='send_message'),
    path('chat/rate-message/', views.rate_message, name='rate_message'),
    
    # Documentos
    path('documents/', views.documents_list, name='documents_list'),
    path('documents/<int:document_id>/', views.document_detail, name='document_detail'),
    path('documents/<int:document_id>/reindex/', views.reindex_document, name='reindex_document'),
    
    # Estadísticas
    path('stats/', views.rag_stats, name='rag_stats'),
]