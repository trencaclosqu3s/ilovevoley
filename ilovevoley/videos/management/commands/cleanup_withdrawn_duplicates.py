from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from ilovevoley.videos.models import Match


class Command(BaseCommand):
    help = 'Elimina partidos withdrawn que son duplicados de otro partido activo (mismo liga+equipos+fecha)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Muestra qué se haría sin hacer cambios')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total_deleted = 0

        # Buscar grupos con más de un partido para la misma combinación liga+local+visitante+día
        # Usamos all_objects para incluir withdrawn
        all_matches = Match.all_objects.select_related('home_team', 'away_team', 'league')

        seen = {}
        for match in all_matches:
            date_key = match.match_date.strftime('%Y-%m-%d') if match.match_date else 'nodate'
            key = (match.league_id, match.home_team_id, match.away_team_id, date_key)
            seen.setdefault(key, []).append(match)

        for key, group in seen.items():
            if len(group) <= 1:
                continue

            def sort_key(m):
                has_results = 1 if (m.home_score is not None and m.away_score is not None) else 0
                has_fed_id = 1 if m.federation_id else 0
                status_score = {'finished': 3, 'scheduled': 2, 'postponed': 1, 'withdrawn': 0}.get(m.status, 1)
                return (has_results, status_score, has_fed_id, m.id)

            group.sort(key=sort_key, reverse=True)
            keeper = group[0]
            tossers = group[1:]

            league_name = keeper.league.name if keeper.league else '?'
            self.stdout.write(
                f"\nDuplicados: {keeper.home_team.name} vs {keeper.away_team.name} "
                f"({key[3]}) - Liga: {league_name}"
            )
            self.stdout.write(
                f"  Conservar: ID {keeper.id} [{keeper.status}] FedID={keeper.federation_id}"
            )

            for tosser in tossers:
                label = f"  Eliminar: ID {tosser.id} [{tosser.status}] FedID={tosser.federation_id}"
                if not dry_run:
                    with transaction.atomic():
                        tosser.delete()
                    self.stdout.write(label)
                    total_deleted += 1
                else:
                    self.stdout.write(f"  [DRY RUN] {label.strip()}")
                    total_deleted += 1

        self.stdout.write(self.style.SUCCESS(f"\nFin. {'Eliminaría' if dry_run else 'Eliminados'} {total_deleted} partidos duplicados."))
