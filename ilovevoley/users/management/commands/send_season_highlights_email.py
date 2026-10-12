"""Envío puntual del mail de novedades de temporada 26/27."""

from django.core.management.base import BaseCommand

from ilovevoley.users.season_highlights import (
    season_highlights_recipients,
    send_season_highlights_email,
)


class Command(BaseCommand):
    help = (
        'Envía (o simula) el mail único de novedades de la temporada 26/27 '
        'a usuarios activos y aprobados con email.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Lista destinatarios sin enviar',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Limitar a un email concreto (prueba)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Máximo de destinatarios (0 = todos)',
        )

    def handle(self, *args, **options):
        qs = season_highlights_recipients()
        email = (options.get('email') or '').strip()
        if email:
            qs = qs.filter(email__iexact=email)
        limit = options.get('limit') or 0
        if limit > 0:
            qs = qs[:limit]

        users = list(qs)
        self.stdout.write(f'Destinatarios: {len(users)}')
        for user in users[:20]:
            self.stdout.write(f'  - {user.email} ({user.username})')
        if len(users) > 20:
            self.stdout.write(f'  … y {len(users) - 20} más')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run: no se ha enviado ningún correo.'))
            return

        ok = 0
        fail = 0
        for user in users:
            if send_season_highlights_email(user):
                ok += 1
            else:
                fail += 1
                self.stderr.write(self.style.ERROR(f'Falló: {user.email}'))

        self.stdout.write(self.style.SUCCESS(f'Enviados: {ok}. Fallidos: {fail}.'))
