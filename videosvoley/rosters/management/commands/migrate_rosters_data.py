from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from videosvoley.videos.models import Person as OldPerson, PlayerRole as OldPlayerRole, StaffRole as OldStaffRole
from videosvoley.rosters.models import Person as NewPerson, PlayerRole as NewPlayerRole, StaffRole as NewStaffRole

class Command(BaseCommand):
    help = 'Migra datos de rosters desde la app videos a la nueva app rosters'

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
            self.style.SUCCESS('Iniciando migración de datos de rosters...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('MODO DRY-RUN: No se realizarán cambios reales')
            )
        
        try:
            with transaction.atomic():
                # Migrar personas primero (sin dependencias)
                self.migrate_persons(dry_run, batch_size)
                
                # Migrar roles de jugador (dependen de personas y equipos)
                self.migrate_player_roles(dry_run, batch_size)
                
                # Migrar roles de staff (dependen de personas y equipos)
                self.migrate_staff_roles(dry_run, batch_size)
                
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

    def migrate_persons(self, dry_run, batch_size):
        """Migrar personas"""
        self.stdout.write('Migrando personas...')
        
        old_persons = OldPerson.objects.all()
        total = old_persons.count()
        
        if total == 0:
            self.stdout.write('No hay personas para migrar')
            return
        
        self.stdout.write(f'Encontradas {total} personas')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_persons[i:i + batch_size]
                for old_person in batch:
                    # Obtener nuevo usuario si existe
                    new_user = None
                    if old_person.user:
                        try:
                            from django.contrib.auth import get_user_model
                            User = get_user_model()
                            new_user = User.objects.get(id=old_person.user.id)
                        except User.DoesNotExist:
                            self.stdout.write(
                                self.style.WARNING(f'Usuario no encontrado: {old_person.user.id}')
                            )
                    
                    NewPerson.objects.get_or_create(
                        id=old_person.id,  # Mantener mismo ID
                        defaults={
                            'first_name': old_person.first_name,
                            'last_name': old_person.last_name,
                            'birth_date': old_person.birth_date,
                            'photo': old_person.photo,
                            'email': old_person.email,
                            'phone': old_person.phone,
                            'user': new_user,
                            'notes': old_person.notes,
                            'is_active': old_person.is_active,
                            'created_at': old_person.created_at,
                            'updated_at': old_person.updated_at,
                        }
                    )
                self.stdout.write(f'Procesadas {min(i + batch_size, total)} personas')
        
        self.stdout.write(
            self.style.SUCCESS(f'Personas migradas: {total}')
        )

    def migrate_player_roles(self, dry_run, batch_size):
        """Migrar roles de jugador"""
        self.stdout.write('Migrando roles de jugador...')
        
        old_roles = OldPlayerRole.objects.select_related('person', 'team').all()
        total = old_roles.count()
        
        if total == 0:
            self.stdout.write('No hay roles de jugador para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} roles de jugador')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_roles[i:i + batch_size]
                for old_role in batch:
                    # Obtener nueva persona
                    try:
                        new_person = NewPerson.objects.get(id=old_role.person.id)
                    except NewPerson.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Persona no encontrada: {old_role.person.id}')
                        )
                        continue
                    
                    # Obtener nuevo equipo (temporal - apunta a videos.Team)
                    try:
                        from videosvoley.videos.models import Team
                        new_team = Team.objects.get(id=old_role.team.id)
                    except Team.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Equipo no encontrado: {old_role.team.id}')
                        )
                        continue
                    
                    NewPlayerRole.objects.get_or_create(
                        id=old_role.id,  # Mantener mismo ID
                        defaults={
                            'person': new_person,
                            'team': new_team,
                            'jersey_number': old_role.jersey_number,
                            'position': old_role.position,
                            'is_active': old_role.is_active,
                            'notes': old_role.notes,
                            'created_at': old_role.created_at,
                            'updated_at': old_role.updated_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} roles de jugador')
        
        self.stdout.write(
            self.style.SUCCESS(f'Roles de jugador migrados: {total}')
        )

    def migrate_staff_roles(self, dry_run, batch_size):
        """Migrar roles de staff"""
        self.stdout.write('Migrando roles de staff...')
        
        old_roles = OldStaffRole.objects.select_related('person', 'team').all()
        total = old_roles.count()
        
        if total == 0:
            self.stdout.write('No hay roles de staff para migrar')
            return
        
        self.stdout.write(f'Encontrados {total} roles de staff')
        
        if not dry_run:
            for i in range(0, total, batch_size):
                batch = old_roles[i:i + batch_size]
                for old_role in batch:
                    # Obtener nueva persona
                    try:
                        new_person = NewPerson.objects.get(id=old_role.person.id)
                    except NewPerson.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Persona no encontrada: {old_role.person.id}')
                        )
                        continue
                    
                    # Obtener nuevo equipo (temporal - apunta a videos.Team)
                    try:
                        from videosvoley.videos.models import Team
                        new_team = Team.objects.get(id=old_role.team.id)
                    except Team.DoesNotExist:
                        self.stdout.write(
                            self.style.WARNING(f'Equipo no encontrado: {old_role.team.id}')
                        )
                        continue
                    
                    NewStaffRole.objects.get_or_create(
                        id=old_role.id,  # Mantener mismo ID
                        defaults={
                            'person': new_person,
                            'team': new_team,
                            'role': old_role.role,
                            'is_active': old_role.is_active,
                            'notes': old_role.notes,
                            'created_at': old_role.created_at,
                            'updated_at': old_role.updated_at,
                        }
                    )
                self.stdout.write(f'Procesados {min(i + batch_size, total)} roles de staff')
        
        self.stdout.write(
            self.style.SUCCESS(f'Roles de staff migrados: {total}')
        )