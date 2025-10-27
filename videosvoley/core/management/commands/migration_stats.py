"""
Comando para mostrar estadísticas detalladas de la migración.
Proporciona información sobre el estado actual de los datos migrados.
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = 'Muestra estadísticas detalladas de la migración de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--format',
            choices=['table', 'json', 'csv'],
            default='table',
            help='Formato de salida (default: table)',
        )
        parser.add_argument(
            '--export',
            type=str,
            help='Exportar estadísticas a archivo',
        )

    def handle(self, *args, **options):
        output_format = options['format']
        export_file = options['export']

        self.stdout.write(
            self.style.SUCCESS('📊 Generando estadísticas de migración...')
        )

        stats = self._collect_stats()
        
        if output_format == 'table':
            self._display_table(stats)
        elif output_format == 'json':
            self._display_json(stats)
        elif output_format == 'csv':
            self._display_csv(stats)

        if export_file:
            self._export_stats(stats, export_file, output_format)

    def _collect_stats(self):
        """Recopila estadísticas de todas las tablas"""
        stats = {
            'timestamp': timezone.now().isoformat(),
            'apps': {}
        }

        with connection.cursor() as cursor:
            # Content app
            stats['apps']['content'] = {
                'name': 'Content',
                'tables': {
                    'categories': self._get_table_stats(cursor, 'content_category'),
                    'videos': self._get_table_stats(cursor, 'content_video'),
                    'images': self._get_table_stats(cursor, 'content_image'),
                    'comments': self._get_table_stats(cursor, 'content_comment'),
                }
            }

            # Teams app
            stats['apps']['teams'] = {
                'name': 'Teams',
                'tables': {
                    'teams': self._get_table_stats(cursor, 'teams_team'),
                    'clubs': self._get_table_stats(cursor, 'teams_club'),
                }
            }

            # Competitions app
            stats['apps']['competitions'] = {
                'name': 'Competitions',
                'tables': {
                    'leagues': self._get_table_stats(cursor, 'competitions_league'),
                    'matches': self._get_table_stats(cursor, 'competitions_match'),
                    'standings': self._get_table_stats(cursor, 'competitions_standing'),
                    'scraping_endpoints': self._get_table_stats(cursor, 'competitions_scrapingendpoint'),
                }
            }

            # Rosters app
            stats['apps']['rosters'] = {
                'name': 'Rosters',
                'tables': {
                    'persons': self._get_table_stats(cursor, 'rosters_person'),
                    'player_roles': self._get_table_stats(cursor, 'rosters_playerrole'),
                    'staff_roles': self._get_table_stats(cursor, 'rosters_staffrole'),
                }
            }

            # Calcular totales
            stats['totals'] = self._calculate_totals(stats['apps'])

        return stats

    def _get_table_stats(self, cursor, table_name):
        """Obtiene estadísticas de una tabla específica"""
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
            count = cursor.fetchone()[0]
            
            # Obtener fecha de creación más reciente
            cursor.execute(f'SELECT MAX(created_at) FROM {table_name}')
            latest_created = cursor.fetchone()[0]
            
            # Obtener fecha de modificación más reciente
            cursor.execute(f'SELECT MAX(modified_at) FROM {table_name}')
            latest_modified = cursor.fetchone()[0]
            
            return {
                'count': count,
                'latest_created': latest_created.isoformat() if latest_created else None,
                'latest_modified': latest_modified.isoformat() if latest_modified else None,
                'status': 'active' if count > 0 else 'empty'
            }
        except Exception as e:
            return {
                'count': 0,
                'latest_created': None,
                'latest_modified': None,
                'status': 'error',
                'error': str(e)
            }

    def _calculate_totals(self, apps):
        """Calcula totales generales"""
        totals = {
            'total_records': 0,
            'total_tables': 0,
            'active_tables': 0,
            'empty_tables': 0,
            'error_tables': 0
        }

        for app_name, app_data in apps.items():
            for table_name, table_stats in app_data['tables'].items():
                totals['total_tables'] += 1
                totals['total_records'] += table_stats['count']
                
                if table_stats['status'] == 'active':
                    totals['active_tables'] += 1
                elif table_stats['status'] == 'empty':
                    totals['empty_tables'] += 1
                elif table_stats['status'] == 'error':
                    totals['error_tables'] += 1

        return totals

    def _display_table(self, stats):
        """Muestra estadísticas en formato tabla"""
        self.stdout.write('\n' + '='*80)
        self.stdout.write('📊 ESTADÍSTICAS DE MIGRACIÓN DE DATOS')
        self.stdout.write('='*80)
        self.stdout.write(f'📅 Generado: {stats["timestamp"]}')
        self.stdout.write('')

        for app_name, app_data in stats['apps'].items():
            self.stdout.write(f'📦 {app_data["name"].upper()}')
            self.stdout.write('-' * 40)
            
            for table_name, table_stats in app_data['tables'].items():
                status_icon = {
                    'active': '✅',
                    'empty': '⚪',
                    'error': '❌'
                }.get(table_stats['status'], '❓')
                
                self.stdout.write(
                    f'  {status_icon} {table_name:<20} {table_stats["count"]:>8} registros'
                )
                
                if table_stats['status'] == 'error':
                    self.stdout.write(f'      Error: {table_stats.get("error", "Desconocido")}')
            
            self.stdout.write('')

        # Totales
        totals = stats['totals']
        self.stdout.write('📈 TOTALES')
        self.stdout.write('-' * 40)
        self.stdout.write(f'  Total de registros: {totals["total_records"]:,}')
        self.stdout.write(f'  Total de tablas: {totals["total_tables"]}')
        self.stdout.write(f'  Tablas activas: {totals["active_tables"]}')
        self.stdout.write(f'  Tablas vacías: {totals["empty_tables"]}')
        self.stdout.write(f'  Tablas con error: {totals["error_tables"]}')

    def _display_json(self, stats):
        """Muestra estadísticas en formato JSON"""
        import json
        self.stdout.write(json.dumps(stats, indent=2, ensure_ascii=False))

    def _display_csv(self, stats):
        """Muestra estadísticas en formato CSV"""
        self.stdout.write('app,table,count,status,latest_created,latest_modified')
        
        for app_name, app_data in stats['apps'].items():
            for table_name, table_stats in app_data['tables'].items():
                self.stdout.write(
                    f'{app_name},{table_name},{table_stats["count"]},'
                    f'{table_stats["status"]},{table_stats["latest_created"]},'
                    f'{table_stats["latest_modified"]}'
                )

    def _export_stats(self, stats, filename, format_type):
        """Exporta estadísticas a archivo"""
        try:
            if format_type == 'json':
                import json
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(stats, f, indent=2, ensure_ascii=False)
            elif format_type == 'csv':
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('app,table,count,status,latest_created,latest_modified\n')
                    for app_name, app_data in stats['apps'].items():
                        for table_name, table_stats in app_data['tables'].items():
                            f.write(
                                f'{app_name},{table_name},{table_stats["count"]},'
                                f'{table_stats["status"]},{table_stats["latest_created"]},'
                                f'{table_stats["latest_modified"]}\n'
                            )
            else:  # table format
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write('ESTADÍSTICAS DE MIGRACIÓN DE DATOS\n')
                    f.write('='*50 + '\n')
                    f.write(f'Generado: {stats["timestamp"]}\n\n')
                    
                    for app_name, app_data in stats['apps'].items():
                        f.write(f'{app_name.upper()}\n')
                        f.write('-' * 20 + '\n')
                        for table_name, table_stats in app_data['tables'].items():
                            f.write(f'{table_name}: {table_stats["count"]} registros\n')
                        f.write('\n')
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Estadísticas exportadas a {filename}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error exportando estadísticas: {e}')
            )