from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from videosvoley.videos.models import Team as OldTeam, Club as OldClub
from videosvoley.teams.models import Team as NewTeam, Club as NewClub

class Command(BaseCommand):
    help = 'Migra datos de teams desde la app videos a la nueva app teams'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular migración sin hacer cambios reales',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Tamaño del lote para procesar (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        self.stdout.write(
            self.style.SUCCESS('Iniciando migración de datos de teams...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se realizarán cambios reales')
            )
        
        try:
            with transaction.atomic():
                # Migrar clubs primero (sin dependencias)
                self.migrate_clubs(dry_run, batch_size)
                
                # Migrar equipos (dependen de clubs)
                self.migrate_teams(dry_run, batch_size)
                
                if dry_run:
                    # En dry-run, hacer rollback
                    raise Exception("Dry run - rollback")
                
                self.stdout.write(
                    self.style.SUCCESS('Migración completada exitosamente!')
                )
                
        except Exception as e:
            if not dry_run:
                self.stdout.write(
                    self.style.ERROR(f'Error durante la migración: {e}')
                )
                raise
            else:
                self.stdout.write(
                    self.style.SUCCESS('Dry run completado - no se realizaron cambios')
                )

    def migrate_clubs(self, dry_run, batch_size):
        """Migrar clubs"""
        self.stdout.write('Migrando clubs...')
        
        old_clubs = OldClub.objects.all()
        total = old_clubs.count()
        
        if total == 0:
            self.stdout.write('No hay clubs para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} clubs')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_clubs[i:i + batch_size]
                for old_club in batch:
                    NewClub.objects.get_or_create(
                        id=old_club.id,  # Mantener mismo ID
                        defaults={
                            'federation_id': old_club.federation_id,
                            'official_name': old_club.official_name,
                            'president': old_club.president,
                            'address': old_club.address,
                            'phone': old_club.phone,
                            'email': old_club.email,
                            'venue_name': old_club.venue_name,
                            'venue_address': old_club.venue_address,
                            'province': old_club.province,
                            'instagram': old_club.instagram,
                            'facebook': old_club.facebook,
                            'twitter': old_club.twitter,
                            'website': old_club.website,
                            'logo_url': old_club.logo_url,
                            'created_at': old_club.created_at,
                            'updated_at': old_club.updated_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} clubs')
        
        self.stdout.write(
            self.style.SUCCESS(f'Clubs migrados: {total}')
        )

    def migrate_teams(self, dry_run, batch_size):
        """Migrar equipos"""
        self.stdout.write('Migrando equipos...')
        
        old_teams = OldTeam.objects.select_related('club', 'category').all()
        total = old_teams.count()
        
        if total == 0:
            self.stdout.write('No hay equipos para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} equipos')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_teams[i:i + batch_size]
                for old_team in batch:
                    # Obtener nuevo club
                    new_club = None
                    if old_team.club:
                        try:
                            new_club = NewClub.objects.get(id=old_team.club.id)
                        except NewClub.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Club no encontrado: {old_team.club.id}')
                            )
                            continue
                    
                    # Obtener nueva categoría
                    new_category = None
                    if old_team.category:
                        try:
                            from videosvoley.content.models import Category
                            new_category = Category.objects.get(name=old_team.category.name)
                        except Category.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Categoría no encontrada: {old_team.category.name}')
                            )
                    
                    NewTeam.objects.get_or_create(
                        id=old_team.id,  # Mantener mismo ID
                        defaults={
                            'name': old_team.name,
                            'federation_id': old_team.federation_id,
                            'club': new_club,
                            'sponsor_name': old_team.sponsor_name,
                            'logo_url': old_team.logo_url,
                            'category': new_category,
                            'is_active': old_team.is_active,
                            'created_at': old_team.created_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} equipos')
        
        self.stdout.write(
            self.style.SUCCESS(f'Equipos migrados: {total}')
        )