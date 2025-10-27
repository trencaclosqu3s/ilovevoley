"""
Comando para limpiar datos duplicados después de la migración.
Identifica y elimina registros duplicados basándose en criterios específicos.
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.db import transaction


class Command(BaseCommand):
    help = 'Limpia datos duplicados después de la migración'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar duplicados sin eliminarlos',
        )
        parser.add_argument(
            '--app',
            choices=['content', 'teams', 'competitions', 'rosters', 'all'],
            default='all',
            help='App específica a limpiar (default: all)',
        )
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Eliminar duplicados automáticamente sin confirmación',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        app_filter = options['app']
        auto_fix = options['auto_fix']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  MODO DRY-RUN: No se eliminarán duplicados')
            )

        self.stdout.write(
            self.style.SUCCESS('🧹 Iniciando limpieza de duplicados...')
        )

        # Definir reglas de limpieza por app
        cleanup_rules = {
            'content': [
                {
                    'table': 'content_category',
                    'name': 'Categorías',
                    'criteria': ['name'],
                    'keep': 'first'
                },
                {
                    'table': 'content_video',
                    'name': 'Videos',
                    'criteria': ['youtube_url_id'],
                    'keep': 'first'
                },
                {
                    'table': 'content_image',
                    'name': 'Imágenes',
                    'criteria': ['image'],
                    'keep': 'first'
                }
            ],
            'teams': [
                {
                    'table': 'teams_team',
                    'name': 'Equipos',
                    'criteria': ['name', 'club_id'],
                    'keep': 'first'
                },
                {
                    'table': 'teams_club',
                    'name': 'Clubs',
                    'criteria': ['name'],
                    'keep': 'first'
                }
            ],
            'competitions': [
                {
                    'table': 'competitions_league',
                    'name': 'Ligas',
                    'criteria': ['name', 'season'],
                    'keep': 'first'
                },
                {
                    'table': 'competitions_match',
                    'name': 'Partidos',
                    'criteria': ['league_id', 'home_team_id', 'away_team_id', 'match_date'],
                    'keep': 'first'
                },
                {
                    'table': 'competitions_standing',
                    'name': 'Clasificaciones',
                    'criteria': ['league_id', 'team_id'],
                    'keep': 'first'
                }
            ],
            'rosters': [
                {
                    'table': 'rosters_person',
                    'name': 'Personas',
                    'criteria': ['first_name', 'last_name', 'email'],
                    'keep': 'first'
                },
                {
                    'table': 'rosters_playerrole',
                    'name': 'Roles de jugador',
                    'criteria': ['person_id', 'team_id'],
                    'keep': 'first'
                },
                {
                    'table': 'rosters_staffrole',
                    'name': 'Roles de staff',
                    'criteria': ['person_id', 'team_id'],
                    'keep': 'first'
                }
            ]
        }

        # Filtrar reglas según app seleccionada
        if app_filter != 'all':
            cleanup_rules = {app_filter: cleanup_rules[app_filter]}

        total_duplicates = 0
        total_cleaned = 0

        for app_name, rules in cleanup_rules.items():
            self.stdout.write(f'\n📦 Limpiando {app_name.upper()}...')
            
            for rule in rules:
                duplicates_found = self._cleanup_table(
                    rule, dry_run, auto_fix
                )
                total_duplicates += duplicates_found
                if not dry_run:
                    total_cleaned += duplicates_found

        # Resumen final
        self.stdout.write('\n' + '='*60)
        if dry_run:
            self.stdout.write('📋 RESUMEN DE DUPLICADOS ENCONTRADOS')
            self.stdout.write(f'Total de duplicados encontrados: {total_duplicates}')
            self.stdout.write('💡 Para eliminar duplicados, omitir --dry-run')
        else:
            self.stdout.write('🧹 LIMPIEZA COMPLETADA')
            self.stdout.write(f'Total de duplicados eliminados: {total_cleaned}')
            self.stdout.write('✅ Limpieza completada exitosamente')

    def _cleanup_table(self, rule, dry_run, auto_fix):
        """Limpia duplicados en una tabla específica"""
        table_name = rule['table']
        table_display = rule['name']
        criteria = rule['criteria']
        keep_strategy = rule['keep']

        self.stdout.write(f'  🔍 Analizando {table_display}...')

        with connection.cursor() as cursor:
            # Construir query para encontrar duplicados
            criteria_str = ', '.join(criteria)
            group_by_str = ', '.join(criteria)
            
            # Query para encontrar duplicados
            duplicate_query = f"""
                SELECT {criteria_str}, COUNT(*) as count
                FROM {table_name}
                GROUP BY {group_by_str}
                HAVING COUNT(*) > 1
                ORDER BY count DESC
            """

            cursor.execute(duplicate_query)
            duplicates = cursor.fetchall()

            if not duplicates:
                self.stdout.write(f'    ✅ {table_display}: Sin duplicados')
                return 0

            total_duplicates = sum(row[-1] - 1 for row in duplicates)  # -1 porque mantenemos uno
            self.stdout.write(f'    ⚠️  {table_display}: {len(duplicates)} grupos de duplicados ({total_duplicates} registros a eliminar)')

            if dry_run:
                # Mostrar detalles de duplicados
                for row in duplicates[:5]:  # Mostrar solo los primeros 5
                    criteria_values = row[:-1]
                    count = row[-1]
                    self.stdout.write(f'      - {criteria_values}: {count} copias')
                
                if len(duplicates) > 5:
                    self.stdout.write(f'      ... y {len(duplicates) - 5} grupos más')
                
                return total_duplicates

            # Eliminar duplicados
            if not auto_fix:
                confirm = input(f'    ¿Eliminar {total_duplicates} duplicados de {table_display}? (y/N): ')
                if confirm.lower() != 'y':
                    self.stdout.write(f'    ⏭️  Saltando {table_display}')
                    return 0

            # Eliminar duplicados manteniendo el primero
            with transaction.atomic():
                for row in duplicates:
                    criteria_values = row[:-1]
                    count = row[-1]
                    
                    # Construir WHERE clause
                    where_conditions = []
                    for i, criterion in enumerate(criteria):
                        where_conditions.append(f'{criterion} = %s')
                    
                    where_clause = ' AND '.join(where_conditions)
                    
                    # Eliminar duplicados manteniendo el primero
                    delete_query = f"""
                        DELETE FROM {table_name}
                        WHERE id IN (
                            SELECT id FROM (
                                SELECT id, ROW_NUMBER() OVER (
                                    PARTITION BY {group_by_str}
                                    ORDER BY id
                                ) as rn
                                FROM {table_name}
                                WHERE {where_clause}
                            ) t
                            WHERE rn > 1
                        )
                    """
                    
                    cursor.execute(delete_query, criteria_values)
                    deleted_count = cursor.rowcount
                    
                    if deleted_count > 0:
                        self.stdout.write(f'      ✅ Eliminados {deleted_count} duplicados')

            self.stdout.write(f'    ✅ {table_display}: Limpieza completada')
            return total_duplicates

    def _get_table_info(self, table_name):
        """Obtiene información básica de una tabla"""
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
            count = cursor.fetchone()[0]
            return count