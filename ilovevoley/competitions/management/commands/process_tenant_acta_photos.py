"""Procesa actas en papel de un tenant con alcance acotado (#495).

Reutiliza el scrape de fotos y ``process_acta_photo_batch`` / ``approve_acta_photo``.
No es un backfill general: filtra por organización, temporadas y categorías.

Uso típico Sant Josep infantil/alevín 24-26:

    python manage.py process_tenant_acta_photos \\
        --organization santjosep \\
        --season 2024-25 --season 2025-26 \\
        --category infantil --category alev \\
        --status

    python manage.py process_tenant_acta_photos ... --discover
    python manage.py process_tenant_acta_photos ... --process --limit 50
    python manage.py process_tenant_acta_photos ... --approve-valid
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from ilovevoley.competitions.services.acta_photo import (
    discover_acta_photos_for_matches,
    scoped_acta_photos,
    scoped_tenant_matches,
)
from ilovevoley.competitions.services.acta_review import approve_acta_photo
from ilovevoley.competitions.services.acta_vision import process_acta_photo_batch
from ilovevoley.core.models import Organization


class Command(BaseCommand):
    help = (
        'Descubre, descarga/lee o aprueba actas en papel de un tenant '
        'acotado por temporada y categoría.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization',
            required=True,
            help='Slug del tenant (ej: santjosep)',
        )
        parser.add_argument(
            '--season',
            action='append',
            dest='seasons',
            help='Temporada YYYY-YY (repetible)',
        )
        parser.add_argument(
            '--category',
            action='append',
            dest='categories',
            help='Subcadena de categoría (repetible; ej: infantil, alev)',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Muestra conteos del alcance (por defecto si no hay otra acción)',
        )
        parser.add_argument(
            '--discover',
            action='store_true',
            help='Relee HTML federativo de las ligas del alcance para crear MatchActaPhoto',
        )
        parser.add_argument(
            '--process',
            action='store_true',
            help='Descarga y lee (visión) fotos pendientes del alcance',
        )
        parser.add_argument(
            '--approve-valid',
            action='store_true',
            help='Aprueba fotos pending_review cuyo extracted_data pasa validación',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Máximo de fotos a procesar/aprobar por pasada (default 50)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Segundos entre jornadas en --discover (default 1.0)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo lista partidos/fotos del alcance, sin red ni escrituras',
        )

    def handle(self, *args, **options):
        try:
            organization = Organization.objects.get(slug=options['organization'])
        except Organization.DoesNotExist as exc:
            raise CommandError(f'Organización no encontrada: {options["organization"]}') from exc

        seasons = options.get('seasons') or None
        categories = options.get('categories') or None
        matches = scoped_tenant_matches(
            organization,
            seasons=seasons,
            category_substrings=categories,
        )
        photos = scoped_acta_photos(
            organization,
            seasons=seasons,
            category_substrings=categories,
        )

        actions = [
            options['discover'],
            options['process'],
            options['approve_valid'],
        ]
        if not any(actions):
            options['status'] = True

        self.stdout.write(
            f'Alcance: org={organization.slug} seasons={seasons or "todas"} '
            f'categories={categories or "todas"} → {matches.count()} partidos, '
            f'{photos.count()} fotos'
        )

        if options['dry_run']:
            photo_by_match = {
                p.match_id: p.status
                for p in photos.filter(match_id__in=matches.values('pk'))
            }
            for match in matches.select_related(
                'home_team', 'away_team', 'league__season'
            ).order_by('match_date')[: options['limit']]:
                photo_state = photo_by_match.get(match.id, 'sin-foto')
                season_name = match.league.season.name if match.league_id else '?'
                self.stdout.write(
                    f'[dry-run] match={match.id} {match} '
                    f'season={season_name} '
                    f'acta_html={"sí" if match.acta_html else "no"} foto={photo_state}'
                )
            self.stdout.write(f'{matches.count()} partidos en alcance (listados hasta --limit).')
            return

        if options['status']:
            self._print_status(matches, photos)

        if options['discover']:
            leagues_n = discover_acta_photos_for_matches(matches, delay=options['delay'])
            photos = scoped_acta_photos(
                organization,
                seasons=seasons,
                category_substrings=categories,
            )
            self.stdout.write(self.style.SUCCESS(
                f'Discover: {leagues_n} ligas recorridas; fotos ahora={photos.count()}'
            ))

        if options['process']:
            processed = process_acta_photo_batch(limit=options['limit'], queryset=photos)
            self.stdout.write(self.style.SUCCESS(f'Process: {processed} fotos tratadas'))

        if options['approve_valid']:
            approved, failed = self._approve_valid(photos, limit=options['limit'])
            self.stdout.write(self.style.SUCCESS(
                f'Approve-valid: {approved} aprobadas, {failed} rechazadas por validación'
            ))

    def _print_status(self, matches, photos):
        without_html = matches.exclude(acta_html__gt='').count()
        with_photo = matches.filter(acta_photo__isnull=False).count()
        self.stdout.write(
            f'Partidos: total={matches.count()} sin_acta_html={without_html} con_foto={with_photo}'
        )
        counts = (
            photos.values('status')
            .annotate(n=Count('id'))
            .order_by('status')
        )
        if not counts:
            self.stdout.write('Fotos: (ninguna)')
            return
        counter = Counter({row['status']: row['n'] for row in counts})
        parts = [f'{status}={n}' for status, n in sorted(counter.items())]
        self.stdout.write('Fotos: ' + ', '.join(parts))

    def _approve_valid(self, photos, *, limit: int) -> tuple[int, int]:
        pending = (
            photos.filter(status='pending_review')
            .exclude(extracted_data__isnull=True)
            .select_related('match')
            .order_by('id')[:limit]
        )
        approved = 0
        failed = 0
        for photo in pending:
            ok, errors = approve_acta_photo(photo)
            if ok:
                approved += 1
                self.stdout.write(f'OK photo={photo.id} match={photo.match_id}')
            else:
                failed += 1
                self.stderr.write(f'FAIL photo={photo.id} match={photo.match_id}: {errors}')
        return approved, failed
