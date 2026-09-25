"""
Management command para corregir los timezones de los partidos.
Convierte las fechas guardadas como UTC (que en realidad son hora local)
a Europe/Madrid correctamente.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from ilovevoley.videos.models import Match
from zoneinfo import ZoneInfo


class Command(BaseCommand):
    help = 'Corrige los timezones de los partidos de UTC a Europe/Madrid'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra qué haría sin hacer cambios reales',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 MODO DRY-RUN - No se harán cambios reales'))
        
        madrid_tz = ZoneInfo('Europe/Madrid')
        matches = Match.objects.all()
        
        total = matches.count()
        self.stdout.write(f'📅 Total de partidos a procesar: {total}')
        
        updated = 0
        
        for match in matches:
            # La fecha actual está guardada como UTC pero es realmente hora local
            # Por ejemplo: 11:00:00+00:00 (UTC) es realmente 11:00 hora local
            old_date = match.match_date
            
            # Quitamos el timezone UTC
            naive_date = old_date.replace(tzinfo=None)
            
            # Le ponemos el timezone correcto (Europe/Madrid)
            # Ahora 11:00 será 11:00+01:00 o 11:00+02:00 según verano/invierno
            new_date = timezone.make_aware(naive_date, madrid_tz)
            
            if dry_run:
                self.stdout.write(
                    f'  {match.home_team} vs {match.away_team}\n'
                    f'    Antes: {old_date} ({old_date.tzinfo})\n'
                    f'    Después: {new_date} ({new_date.tzinfo})'
                )
            else:
                match.match_date = new_date
                match.save(update_fields=['match_date'])
            
            updated += 1
            
            if updated % 50 == 0:
                self.stdout.write(f'  Procesados {updated}/{total}...')
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Se procesarían {updated} partidos'))
            self.stdout.write(self.style.WARNING('Ejecuta sin --dry-run para aplicar los cambios'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✅ Se actualizaron {updated} partidos correctamente'))
            self.stdout.write(self.style.SUCCESS('🎉 Todos los timezones han sido corregidos'))
