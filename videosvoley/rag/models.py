from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Document(models.Model):
    """Modelo para almacenar documentos indexados en el sistema RAG"""
    
    title = models.CharField(max_length=500, verbose_name="Título")
    content = models.TextField(verbose_name="Contenido")
    source_type = models.CharField(
        max_length=50,
        choices=[
            ('video', 'Video'),
            ('image', 'Imagen'),
            ('match', 'Partido'),
            ('league', 'Liga'),
            ('manual', 'Manual'),
        ],
        verbose_name="Tipo de fuente"
    )
    source_id = models.PositiveIntegerField(
        null=True, 
        blank=True, 
        verbose_name="ID de la fuente"
    )
    metadata = models.JSONField(
        default=dict, 
        blank=True, 
        verbose_name="Metadatos"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")
    is_indexed = models.BooleanField(default=False, verbose_name="Indexado")
    
    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class ChatSession(models.Model):
    """Modelo para almacenar sesiones de chat con el sistema RAG"""
    
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        verbose_name="Usuario"
    )
    title = models.CharField(max_length=200, verbose_name="Título de la sesión")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")
    
    class Meta:
        verbose_name = "Sesión de Chat"
        verbose_name_plural = "Sesiones de Chat"
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"


class ChatMessage(models.Model):
    """Modelo para almacenar mensajes de chat"""
    
    session = models.ForeignKey(
        ChatSession, 
        on_delete=models.CASCADE, 
        related_name='messages',
        verbose_name="Sesión"
    )
    role = models.CharField(
        max_length=10,
        choices=[
            ('user', 'Usuario'),
            ('assistant', 'Asistente'),
        ],
        verbose_name="Rol"
    )
    content = models.TextField(verbose_name="Contenido")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    
    class Meta:
        verbose_name = "Mensaje de Chat"
        verbose_name_plural = "Mensajes de Chat"
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."