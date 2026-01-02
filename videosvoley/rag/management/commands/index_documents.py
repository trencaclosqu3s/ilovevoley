from django.core.management.base import BaseCommand, CommandError
from django.db import models
from videosvoley.videos.models import Video, Image, Match, League, Standing
from videosvoley.rag.models import Document
from videosvoley.rag.services import get_rag_service
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Indexar documentos del sistema VideosVoley en ChromaDB para RAG'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-type',
            type=str,
            choices=['video', 'image', 'match', 'league', 'standing', 'manual', 'all'],
            default='all',
            help='Tipo de fuente a indexar (default: all)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Límite de documentos a procesar'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forzar reindexación de documentos ya indexados'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se indexaría sin hacer cambios'
        )
        parser.add_argument(
            '--incremental',
            action='store_true',
            help='Solo indexar elementos nuevos o modificados desde la última indexación'
        )

    def handle(self, *args, **options):
        source_type = options['source_type']
        limit = options.get('limit')
        force = options['force']
        dry_run = options['dry_run']
        incremental = options['incremental']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY RUN - No se realizarán cambios')
            )

        try:
            total_indexed = 0

            if source_type in ['video', 'all']:
                try:
                    total_indexed += self._index_videos(limit, force, dry_run, incremental)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando videos: {e}')
                    )

            if source_type in ['image', 'all']:
                try:
                    total_indexed += self._index_images(limit, force, dry_run, incremental)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando imágenes: {e}')
                    )

            if source_type in ['match', 'all']:
                try:
                    total_indexed += self._index_matches(limit, force, dry_run, incremental)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando partidos: {e}')
                    )

            if source_type in ['league', 'all']:
                try:
                    total_indexed += self._index_leagues(limit, force, dry_run, incremental)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando ligas: {e}')
                    )

            if source_type in ['standing', 'all']:
                try:
                    total_indexed += self._index_standings(limit, force, dry_run, incremental)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando clasificaciones: {e}')
                    )

            if source_type in ['manual', 'all']:
                try:
                    total_indexed += self._index_manuals(limit, force, dry_run)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando documentos manuales: {e}')
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Proceso completado. Total indexado: {total_indexed} documentos'
                )
            )

        except Exception as e:
            logger.error(f"Error general en indexación: {e}")
            self.stdout.write(
                self.style.ERROR(f'Error general durante la indexación: {e}')
            )

    def _index_videos(self, limit, force, dry_run, incremental=False):
        """Indexar videos"""
        self.stdout.write('Indexando videos...')
        
        videos = Video.objects.all()
        if limit:
            videos = videos[:limit]

        indexed = 0
        for video in videos:
            if not force and Document.objects.filter(
                source_type='video', 
                source_id=video.id, 
                is_indexed=True
            ).exists():
                continue

            content = self._create_video_content(video)
            metadata = {
                'title': video.title,
                'source_type': 'video',
                'source_id': video.id,
                'category': video.category.name if video.category else None,
                'youtube_url': video.youtube_url,
                'created_at': video.created_at.isoformat(),
            }

            if not dry_run:
                # Crear o actualizar documento
                doc, created = Document.objects.get_or_create(
                    source_type='video',
                    source_id=video.id,
                    defaults={
                        'title': video.title,
                        'content': content,
                        'metadata': metadata
                    }
                )
                
                if not created:
                    doc.title = video.title
                    doc.content = content
                    doc.metadata = metadata
                    doc.is_indexed = False
                    doc.save()

                # Indexar en ChromaDB
                rag_service = get_rag_service()
                rag_service = get_rag_service()
                success = rag_service.add_document(
                    document_id=str(doc.id),
                    content=content,
                    metadata=metadata
                )

                if success:
                    doc.is_indexed = True
                    doc.save()
                    indexed += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(f'Error indexando video {video.id}')
                    )
            else:
                self.stdout.write(f'  - Video: {video.title}')
                indexed += 1

        self.stdout.write(f'Videos procesados: {indexed}')
        return indexed

    def _index_images(self, limit, force, dry_run, incremental=False):
        """Indexar imágenes"""
        self.stdout.write('Indexando imágenes...')
        
        images = Image.objects.all()
        if limit:
            images = images[:limit]

        indexed = 0
        for image in images:
            try:
                if not force and Document.objects.filter(
                    source_type='image', 
                    source_id=image.id, 
                    is_indexed=True
                ).exists():
                    continue

                content = self._create_image_content(image)
                metadata = {
                    'title': f"Imagen: {image.image_type}",
                    'source_type': 'image',
                    'source_id': image.id,
                    'image_type': image.image_type,
                    'match': str(image.match) if image.match else 'Sin partido',
                    'created_at': image.upload_date.isoformat() if image.upload_date else 'Sin fecha',
                }

                if not dry_run:
                    doc, created = Document.objects.get_or_create(
                        source_type='image',
                        source_id=image.id,
                        defaults={
                            'title': f"Imagen: {image.image_type}",
                            'content': content,
                            'metadata': metadata
                        }
                    )
                    
                    if not created:
                        doc.title = f"Imagen: {image.image_type}"
                        doc.content = content
                        doc.metadata = metadata
                        doc.is_indexed = False
                        doc.save()

                    rag_service = get_rag_service()
                    success = rag_service.add_document(
                        document_id=str(doc.id),
                        content=content,
                        metadata=metadata
                    )

                    if success:
                        doc.is_indexed = True
                        doc.save()
                        indexed += 1
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'Error indexando imagen {image.id}')
                        )
                else:
                    self.stdout.write(f'  - Imagen: {image.image_type}')
                    indexed += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Error procesando imagen {image.id}: {e}')
                )
                continue

        self.stdout.write(f'Imágenes procesadas: {indexed}')
        return indexed

    def _index_matches(self, limit, force, dry_run, incremental=False):
        """Indexar partidos"""
        self.stdout.write('Indexando partidos...')
        
        matches = Match.objects.all().order_by('-id')
        
        # Filtro incremental: solo partidos nuevos
        if incremental and not force:
            # Obtener el ID más alto de los documentos ya indexados
            last_indexed = Document.objects.filter(
                source_type='match', 
                is_indexed=True
            ).aggregate(max_id=models.Max('source_id'))['max_id']
            
            if last_indexed:
                matches = matches.filter(id__gt=last_indexed)
                self.stdout.write(f'Modo incremental: procesando partidos desde ID {last_indexed + 1}')
            else:
                self.stdout.write('Modo incremental: no hay partidos previamente indexados')
        
        if limit:
            matches = matches[:limit]

        indexed = 0
        for match in matches:
            try:
                if not force and not incremental and Document.objects.filter(
                    source_type='match', 
                    source_id=match.id, 
                    is_indexed=True
                ).exists():
                    continue

                content = self._create_match_content(match)
                metadata = {
                    'title': f"{match.home_team} vs {match.away_team}",
                    'source_type': 'match',
                    'source_id': match.id,
                    'league': str(match.league) if match.league else 'Sin liga',
                    'date': match.match_date.isoformat() if match.match_date else 'Sin fecha',
                    'venue': match.venue or 'Sin lugar',
                    'created_at': match.created_at.isoformat() if match.created_at else 'Sin fecha',
                }

                if not dry_run:
                    doc, created = Document.objects.get_or_create(
                        source_type='match',
                        source_id=match.id,
                        defaults={
                            'title': f"{match.home_team} vs {match.away_team}",
                            'content': content,
                            'metadata': metadata
                        }
                    )
                    
                    if not created:
                        doc.title = f"{match.home_team} vs {match.away_team}"
                        doc.content = content
                        doc.metadata = metadata
                        doc.is_indexed = False
                        doc.save()

                    rag_service = get_rag_service()
                    success = rag_service.add_document(
                        document_id=str(doc.id),
                        content=content,
                        metadata=metadata
                    )

                    if success:
                        doc.is_indexed = True
                        doc.save()
                        indexed += 1
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'Error indexando partido {match.id}')
                        )
                else:
                    self.stdout.write(f'  - Partido: {match.home_team} vs {match.away_team}')
                    indexed += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Error procesando partido {match.id}: {e}')
                )
                continue

        self.stdout.write(f'Partidos procesados: {indexed}')
        return indexed

    def _index_leagues(self, limit, force, dry_run, incremental=False):
        """Indexar ligas"""
        self.stdout.write('Indexando ligas...')
        
        leagues = League.objects.all()
        if limit:
            leagues = leagues[:limit]

        indexed = 0
        for league in leagues:
            try:
                if not force and Document.objects.filter(
                    source_type='league', 
                    source_id=league.id, 
                    is_indexed=True
                ).exists():
                    continue

                content = self._create_league_content(league)
                # Obtener nombres de todas las categorías
                categories = league.categories.all()
                category_names = ', '.join([c.name for c in categories]) if categories else 'Sin categoría'
                metadata = {
                    'title': league.name,
                    'source_type': 'league',
                    'source_id': league.id,
                    'category': category_names,
                    'season': league.season or 'Sin temporada',
                    'created_at': league.created_at.isoformat() if league.created_at else 'Sin fecha',
                }

                if not dry_run:
                    doc, created = Document.objects.get_or_create(
                        source_type='league',
                        source_id=league.id,
                        defaults={
                            'title': league.name,
                            'content': content,
                            'metadata': metadata
                        }
                    )
                    
                    if not created:
                        doc.title = league.name
                        doc.content = content
                        doc.metadata = metadata
                        doc.is_indexed = False
                        doc.save()

                    rag_service = get_rag_service()
                    success = rag_service.add_document(
                        document_id=str(doc.id),
                        content=content,
                        metadata=metadata
                    )

                    if success:
                        doc.is_indexed = True
                        doc.save()
                        indexed += 1
                    else:
                        self.stdout.write(
                            self.style.ERROR(f'Error indexando liga {league.id}')
                        )
                else:
                    self.stdout.write(f'  - Liga: {league.name}')
                    indexed += 1
                    
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Error procesando liga {league.id}: {e}')
                )
                continue

        self.stdout.write(f'Ligas procesadas: {indexed}')
        return indexed

    def _index_manuals(self, limit, force, dry_run, incremental=False):
        """Indexar documentos manuales (por ejemplo, reglamentos) ya almacenados en BD"""
        self.stdout.write('Indexando documentos manuales...')

        manuals = Document.objects.filter(source_type='manual')
        if not force:
            manuals = manuals.filter(is_indexed=False)
        if limit:
            manuals = manuals[:limit]

        indexed = 0
        for doc in manuals:
            metadata = {
                'title': doc.title,
                'source_type': doc.source_type,
                'source_id': doc.source_id,
                'created_at': doc.created_at.isoformat() if doc.created_at else None,
                **(doc.metadata or {})
            }

            if dry_run:
                self.stdout.write(f"  - Manual: {doc.title}")
                indexed += 1
                continue

            rag_service = get_rag_service()
            success = rag_service.add_document(
                document_id=str(doc.id),
                content=doc.content,
                metadata=metadata
            )

            if success:
                doc.is_indexed = True
                doc.save()
                indexed += 1
            else:
                self.stdout.write(
                    self.style.ERROR(f'Error indexando manual {doc.id}')
                )

        self.stdout.write(f'Manuales procesados: {indexed}')
        return indexed

    def _create_video_content(self, video):
        """Crear contenido para indexar de un video"""
        content_parts = [
            f"Título: {video.title}",
            f"Descripción: {video.description or 'Sin descripción'}",
        ]
        
        if video.category:
            content_parts.append(f"Categoría: {video.category.name}")
        
        if video.youtube_url:
            content_parts.append(f"URL de YouTube: {video.youtube_url}")
        
        if video.match:
            content_parts.append(f"Partido relacionado: {video.match}")
        
        if video.comments.exists():
            comments_text = " ".join([c.content for c in video.comments.all()])
            content_parts.append(f"Comentarios: {comments_text}")
        
        return " | ".join(content_parts)

    def _create_image_content(self, image):
        """Crear contenido para indexar de una imagen"""
        content_parts = [
            f"Tipo de imagen: {image.image_type}",
            f"Descripción: {image.description or 'Sin descripción'}",
        ]
        
        if image.match:
            content_parts.append(f"Partido relacionado: {image.match}")
        
        if image.tags:
            content_parts.append(f"Etiquetas: {', '.join(image.tags)}")
        
        return " | ".join(content_parts)

    def _create_match_content(self, match):
        """Crear contenido para indexar de un partido"""
        content_parts = [
            f"Partido: {match.home_team} vs {match.away_team}",
        ]
        
        if match.league:
            content_parts.append(f"Liga: {match.league.name}")
        
        if match.match_date:
            content_parts.append(f"Fecha: {match.match_date.strftime('%d/%m/%Y')}")
        
        if match.venue:
            content_parts.append(f"Lugar: {match.venue}")
        
        if match.home_score is not None and match.away_score is not None:
            content_parts.append(f"Resultado: {match.home_score} - {match.away_score}")
        
        if match.round_number:
            content_parts.append(f"Jornada: {match.round_number}")
        
        return " | ".join(content_parts)

    def _create_league_content(self, league):
        """Crear contenido para indexar de una liga"""
        # Obtener nombres de todas las categorías
        categories = league.categories.all()
        category_names = ', '.join([c.name for c in categories]) if categories else 'Sin categoría'
        content_parts = [
            f"Liga: {league.name}",
            f"Categoría: {category_names}",
            f"Temporada: {league.season}",
        ]
        
        # El modelo League no tiene campo description, lo omitimos
        
        return " | ".join(content_parts)

    def _index_standings(self, limit, force, dry_run, incremental=False):
        """Indexar clasificaciones"""
        self.stdout.write('Indexando clasificaciones...')
        
        standings = Standing.objects.select_related('league', 'team').all()
        if limit:
            standings = standings[:limit]

        indexed = 0
        for standing in standings:
            if not force and Document.objects.filter(
                source_type='standing', 
                source_id=standing.id, 
                is_indexed=True
            ).exists():
                continue

            content = self._create_standing_content(standing)
            # Obtener nombres de todas las categorías
            categories = standing.league.categories.all()
            category_names = ', '.join([c.name for c in categories]) if categories else None
            metadata = {
                'league_name': standing.league.name,
                'team_name': standing.team.name,
                'position': standing.position,
                'total_points': standing.total_points,
                'source_type': 'standing',
                'source_id': standing.id,
                'category': category_names,
            }

            if not dry_run:
                # Crear o actualizar documento
                doc, created = Document.objects.get_or_create(
                    source_type='standing',
                    source_id=standing.id,
                    defaults={
                        'title': f'Clasificación {standing.league.name} - {standing.team.name}',
                        'content': content,
                        'metadata': metadata
                    }
                )
                
                if not created:
                    doc.title = f'Clasificación {standing.league.name} - {standing.team.name}'
                    doc.content = content
                    doc.metadata = metadata
                    doc.is_indexed = False
                    doc.save()

                # Indexar en ChromaDB
                rag_service = get_rag_service()
                success = rag_service.add_document(
                    document_id=str(doc.id),
                    content=content,
                    metadata=metadata
                )

                if success:
                    doc.is_indexed = True
                    doc.save()
                    indexed += 1

            else:
                self.stdout.write(f'[DRY RUN] Indexaría: {content[:100]}...')
                indexed += 1

        self.stdout.write(f'Clasificaciones procesadas: {indexed}')
        return indexed

    def _create_standing_content(self, standing):
        """Crear contenido para indexar de una clasificación"""
        content_parts = [
            f"Clasificación Liga: {standing.league.name}",
            f"Equipo: {standing.team.name}",
            f"Posición: {standing.position}",
            f"Partidos jugados: {standing.played}",
            f"Partidos ganados: {standing.won}",
            f"Partidos perdidos: {standing.lost}",
            f"Sets a favor: {standing.sets_for}",
            f"Sets en contra: {standing.sets_against}",
            f"Puntos totales: {standing.total_points}",
        ]

        # Agregar categorías si existen
        categories = standing.league.categories.all()
        if categories:
            category_names = ', '.join([c.name for c in categories])
            content_parts.append(f"Categoría: {category_names}")
        
        return " | ".join(content_parts)