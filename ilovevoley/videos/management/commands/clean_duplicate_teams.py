"""
Comando para limpiar equipos duplicados basados en nombres normalizados
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from ilovevoley.videos.models import Team
from ilovevoley.videos.utils import normalize_team_name


class Command(BaseCommand):
    help = 'Limpia equipos duplicados basados en nombres normalizados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin hacer cambios reales',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar información detallada',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY RUN - No se harán cambios reales'))
        
        self.stdout.write('Buscando equipos duplicados...')
        
        # Obtener todos los equipos activos
        teams = Team.objects.filter(is_active=True).order_by('name')
        processed_teams = set()
        duplicates_found = []
        
        for team in teams:
            if team.id in processed_teams:
                continue
                
            team_normalized = normalize_team_name(team.name)
            duplicates = []
            
            # Buscar otros equipos con el mismo nombre normalizado
            for other_team in teams:
                if (other_team.id != team.id and 
                    other_team.id not in processed_teams and
                    normalize_team_name(other_team.name) == team_normalized):
                    duplicates.append(other_team)
            
            if duplicates:
                # El equipo actual + sus duplicados
                all_duplicates = [team] + duplicates
                duplicates_found.append(all_duplicates)
                
                # Marcar todos como procesados
                for dup_team in all_duplicates:
                    processed_teams.add(dup_team.id)
        
        if not duplicates_found:
            self.stdout.write(self.style.SUCCESS('No se encontraron equipos duplicados'))
            return
        
        self.stdout.write(f'\\nEncontrados {len(duplicates_found)} grupos de equipos duplicados:')
        
        for i, group in enumerate(duplicates_found, 1):
            self.stdout.write(f'\\nGrupo {i}:')
            for team in group:
                self.stdout.write(f'  - ID {team.id}: "{team.name}" (federation_id: {team.federation_id})')
            
            # Elegir el equipo principal (el que tiene federation_id o el más antiguo)
            main_team = None
            for team in group:
                if team.federation_id:
                    main_team = team
                    break
            
            if not main_team:
                main_team = min(group, key=lambda t: t.id)  # El más antiguo
            
            self.stdout.write(f'  → Equipo principal elegido: ID {main_team.id} "{main_team.name}"')
            
            if not dry_run:
                with transaction.atomic():
                    # Actualizar los duplicados para que apunten al equipo principal
                    for team in group:
                        if team.id != main_team.id:
                            if verbose:
                                self.stdout.write(f'    Eliminando duplicado: ID {team.id} "{team.name}"')
                            
                            # Marcar como inactivo en lugar de eliminar para preservar referencias
                            team.is_active = False
                            team.save()
                            
                            # Si el duplicado tenía federation_id, actualizarlo al principal
                            if team.federation_id and not main_team.federation_id:
                                main_team.federation_id = team.federation_id
                                main_team.save()
                                if verbose:
                                    self.stdout.write(f'    Transferido federation_id {team.federation_id} al equipo principal')
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'\\n[DRY RUN] Se procesarían {len(duplicates_found)} grupos de duplicados'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\\nProcesados {len(duplicates_found)} grupos de duplicados'))