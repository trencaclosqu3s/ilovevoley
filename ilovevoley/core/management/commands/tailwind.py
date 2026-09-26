import pathlib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from scripts.build_tailwind import compile_tailwind, ensure_binary


class Command(BaseCommand):
    help = "Compila o vigila el CSS de Tailwind utilizando el binario standalone CLI oficial."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            nargs="?",
            default="build",
            choices=["build", "watch", "download"],
            help="Acción a realizar: build (compilar), watch (vigilar cambios), download (solo descargar binario)",
        )
        parser.add_argument(
            "--no-minify",
            action="store_true",
            default=False,
            help="Desactivar minificación en el build.",
        )
        parser.add_argument(
            "--watch",
            action="store_true",
            default=False,
            help="Vigilar cambios en los archivos (equivalente a action='watch').",
        )

    def handle(self, *args, **options):
        base_dir = pathlib.Path(settings.BASE_DIR)
        action = options["action"]
        watch_mode = options["watch"] or action == "watch"

        if action == "download":
            ensure_binary(base_dir / ".bin", stdout=self.stdout)
            self.stdout.write(self.style.SUCCESS("Binario descargado correctamente."))
            return

        try:
            compile_tailwind(
                base_dir=base_dir,
                watch=watch_mode,
                minify=not options["no_minify"],
                stdout=self.stdout,
            )
        except Exception as e:
            raise CommandError(str(e))
