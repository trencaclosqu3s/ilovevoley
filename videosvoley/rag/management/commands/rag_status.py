from django.core.management.base import BaseCommand
from django.db import models
from videosvoley.content.models import Video, Image
from videosvoley.competitions.models import Match, League, Standing
from videosvoley.rag.models import Document
from videosvoley.rag.services import get_rag_service
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Mostrar estado del sistema RAG y estadísticas de indexación'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🔍 Estado del Sistema RAG - VideosVoley')
        )
        self.stdout.write('=' * 50)
        
        # Estadísticas de ChromaDB
        try:
            rag_service = get_rag_service()
            stats = rag_service.get_collection_stats()
            self.stdout.write(
                f"📊 Total documentos en ChromaDB: {stats['total_documents']}"
            )
            self.stdout.write(
                f"🗂️  Colección: {stats['collection_name']}"
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Error conectando con ChromaDB: {e}")
            )
        
        self.stdout.write('')
        
        # Estadísticas por tipo de documento
        self._show_document_stats()
        
        self.stdout.write('')
        
        # Elementos pendientes de indexar
        self._show_pending_items()
        
        self.stdout.write('')
        
        # Última actividad
        self._show_recent_activity()

    def _show_document_stats(self):
        """Mostrar estadísticas de documentos indexados"""
        self.stdout.write(self.style.SUCCESS('📈 Documentos Indexados:'))
        
        doc_types = ['match', 'standing', 'video', 'image', 'league']
        
        for doc_type in doc_types:
            count = Document.objects.filter(
                source_type=doc_type,
                is_indexed=True
            ).count()
            
            # Emoji según el tipo
            emoji = {
                'match': '⚽',
                'standing': '🏆', 
                'video': '🎥',
                'image': '🖼️',
                'league': '🏟️'
            }.get(doc_type, '📄')
            
            self.stdout.write(f"   {emoji} {doc_type.title()}: {count}")

    def _show_pending_items(self):
        """Mostrar elementos pendientes de indexar"""
        self.stdout.write(self.style.WARNING('⏳ Pendientes de Indexar:'))
        
        # Partidos pendientes
        indexed_matches = set(Document.objects.filter(
            source_type='match',
            is_indexed=True
        ).values_list('source_id', flat=True))
        
        total_matches = Match.objects.count()
        pending_matches = total_matches - len(indexed_matches)
        
        if pending_matches > 0:
            # Obtener los últimos partidos no indexados
            latest_pending = Match.objects.exclude(
                id__in=indexed_matches
            ).order_by('-id')[:3]
            
            self.stdout.write(f"   ⚽ Partidos: {pending_matches}")
            for match in latest_pending:
                date_str = match.match_date.strftime('%d/%m/%Y') if match.match_date else 'Sin fecha'
                self.stdout.write(f"      • {match.home_team} vs {match.away_team} ({date_str})")
        else:
            self.stdout.write("   ⚽ Partidos: 0 ✅")
        
        # Clasificaciones pendientes
        indexed_standings = set(Document.objects.filter(
            source_type='standing',
            is_indexed=True
        ).values_list('source_id', flat=True))
        
        total_standings = Standing.objects.count()
        pending_standings = total_standings - len(indexed_standings)
        
        if pending_standings > 0:
            self.stdout.write(f"   🏆 Clasificaciones: {pending_standings}")
        else:
            self.stdout.write("   🏆 Clasificaciones: 0 ✅")

    def _show_recent_activity(self):
        """Mostrar actividad reciente"""
        self.stdout.write(self.style.SUCCESS('📅 Actividad Reciente:'))
        
        # Últimos documentos indexados
        recent_docs = Document.objects.filter(
            is_indexed=True
        ).order_by('-created_at')[:5]
        
        if recent_docs:
            self.stdout.write("   Últimos documentos indexados:")
            for doc in recent_docs:
                created_str = doc.created_at.strftime('%d/%m/%Y %H:%M')
                self.stdout.write(f"      • {doc.source_type}: {doc.title[:50]}... ({created_str})")
        else:
            self.stdout.write("   No hay documentos indexados")
        
        # Sugerencias
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('💡 Comandos Útiles:'))
        self.stdout.write('   python manage.py index_documents --source-type all --incremental')
        self.stdout.write('   python manage.py index_documents --source-type match --force --limit 10')
        self.stdout.write('   python manage.py index_documents --source-type standing --force')