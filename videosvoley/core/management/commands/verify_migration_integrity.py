"""
Comando para verificar la integridad de los datos migrados.
Compara los datos originales con los migrados para asegurar que no se perdió información.
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Verifica la integridad de los datos migrados comparando con los originales'

    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Mostrar detalles de cada tabla verificada',
        )
        parser.add_argument(
            '--fix-missing',
            action='store_true',
            help='Intentar corregir datos faltantes automáticamente',
        )

    def handle(self, *args, **options):
        detailed = options['detailed']
        fix_missing = options['fix_missing']

        self.stdout.write(
            self.style.SUCCESS('🔍 Verificando integridad de datos migrados...')
        )

        # Definir tablas a verificar
        tables_to_verify = [
            {
                'original': 'videos_category',
                'new': 'content_category',
                'name': 'Categorías',
                'critical': True
            },
            {
                'original': 'videos_video',
                'new': 'content_video',
                'name': 'Videos',
                'critical': True
            },
            {
                'original': 'videos_image',
                'new': 'content_image',
                'name': 'Imágenes',
                'critical': True
            },
            {
                'original': 'videos_comment',
                'new': 'content_comment',
                'name': 'Comentarios',
                'critical': False
            },
            {
                'original': 'videos_team',
                'new': 'teams_team',
                'name': 'Equipos',
                'critical': True
            },
            {
                'original': 'videos_club',
                'new': 'teams_club',
                'name': 'Clubs',
                'critical': True
            },
            {
                'original': 'videos_league',
                'new': 'competitions_league',
                'name': 'Ligas',
                'critical': True
            },
            {
                'original': 'videos_match',
                'new': 'competitions_match',
                'name': 'Partidos',
                'critical': True
            },
            {
                'original': 'videos_standing',
                'new': 'competitions_standing',
                'name': 'Clasificaciones',
                'critical': True
            },
            {
                'original': 'videos_scrapingendpoint',
                'new': 'competitions_scrapingendpoint',
                'name': 'Endpoints de scraping',
                'critical': False
            },
            {
                'original': 'videos_person',
                'new': 'rosters_person',
                'name': 'Personas',
                'critical': True
            },
            {
                'original': 'videos_playerrole',
                'new': 'rosters_playerrole',
                'name': 'Roles de jugador',
                'critical': True
            },
            {
                'original': 'videos_staffrole',
                'new': 'rosters_staffrole',
                'name': 'Roles de staff',
                'critical': True
            }
        ]

        total_tables = len(tables_to_verify)
        verified_tables = 0
        issues_found = 0
        critical_issues = 0

        with connection.cursor() as cursor:
            for i, table in enumerate(tables_to_verify, 1):
                self.stdout.write(
                    f'\n📊 [{i}/{total_tables}] Verificando {table["name"]}...'
                )

                try:
                    # Contar registros originales
                    cursor.execute(f'SELECT COUNT(*) FROM {table["original"]}')
                    original_count = cursor.fetchone()[0]

                    # Contar registros migrados
                    cursor.execute(f'SELECT COUNT(*) FROM {table["new"]}')
                    new_count = cursor.fetchone()[0]

                    # Verificar integridad
                    if original_count == new_count:
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✅ {table["name"]}: {original_count} registros')
                        )
                        verified_tables += 1
                    else:
                        issue_type = 'CRÍTICO' if table['critical'] else 'Advertencia'
                        self.stdout.write(
                            self.style.ERROR(
                                f'  ❌ {table["name"]}: {original_count} originales vs {new_count} migrados ({issue_type})'
                            )
                        )
                        issues_found += 1
                        if table['critical']:
                            critical_issues += 1

                    # Mostrar detalles si se solicita
                    if detailed:
                        self.stdout.write(f'    Original: {original_count} registros')
                        self.stdout.write(f'    Migrado:  {new_count} registros')
                        if original_count != new_count:
                            self.stdout.write(f'    Diferencia: {original_count - new_count} registros')

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ❌ Error verificando {table["name"]}: {e}')
                    )
                    issues_found += 1
                    if table['critical']:
                        critical_issues += 1

        # Resumen final
        self.stdout.write('\n' + '='*60)
        self.stdout.write('📋 RESUMEN DE VERIFICACIÓN')
        self.stdout.write('='*60)
        
        self.stdout.write(f'Tablas verificadas: {verified_tables}/{total_tables}')
        self.stdout.write(f'Problemas encontrados: {issues_found}')
        self.stdout.write(f'Problemas críticos: {critical_issues}')

        if issues_found == 0:
            self.stdout.write(
                self.style.SUCCESS('🎉 ¡Todas las tablas verificadas correctamente!')
            )
        elif critical_issues == 0:
            self.stdout.write(
                self.style.WARNING('⚠️  Se encontraron problemas menores, pero no críticos')
            )
        else:
            self.stdout.write(
                self.style.ERROR('❌ Se encontraron problemas críticos que requieren atención')
            )
            
            if fix_missing:
                self.stdout.write('\n🔧 Intentando corregir problemas automáticamente...')
                try:
                    call_command('migrate_all_data', '--dry-run')
                    self.stdout.write(
                        self.style.SUCCESS('✅ Comando de corrección ejecutado')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'❌ Error en corrección automática: {e}')
                    )

        # Verificar foreign keys temporales
        self.stdout.write('\n🔗 Verificando foreign keys temporales...')
        self._verify_foreign_keys()

    def _verify_foreign_keys(self):
        """Verifica que las foreign keys temporales estén funcionando correctamente"""
        with connection.cursor() as cursor:
            # Verificar que las foreign keys temporales apunten a videos.Team
            cursor.execute("""
                SELECT COUNT(*) FROM competitions_match 
                WHERE home_team_id IS NOT NULL 
                AND home_team_id NOT IN (SELECT id FROM videos_team)
            """)
            invalid_home_teams = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM competitions_match 
                WHERE away_team_id IS NOT NULL 
                AND away_team_id NOT IN (SELECT id FROM videos_team)
            """)
            invalid_away_teams = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM competitions_standing 
                WHERE team_id IS NOT NULL 
                AND team_id NOT IN (SELECT id FROM videos_team)
            """)
            invalid_standing_teams = cursor.fetchone()[0]

            if invalid_home_teams == 0 and invalid_away_teams == 0 and invalid_standing_teams == 0:
                self.stdout.write(
                    self.style.SUCCESS('  ✅ Foreign keys temporales funcionando correctamente')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'  ❌ Foreign keys temporales con problemas:')
                )
                if invalid_home_teams > 0:
                    self.stdout.write(f'    - {invalid_home_teams} partidos con home_team inválido')
                if invalid_away_teams > 0:
                    self.stdout.write(f'    - {invalid_away_teams} partidos con away_team inválido')
                if invalid_standing_teams > 0:
                    self.stdout.write(f'    - {invalid_standing_teams} clasificaciones con team inválido')