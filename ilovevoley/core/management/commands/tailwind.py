import hashlib
import os
import pathlib
import platform
import subprocess
import urllib.request
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

TAILWIND_VERSION = "3.4.17"

TAILWIND_SHA256 = {
    "tailwindcss-linux-arm64": "69b1378b8133192d7d2feb12a116fa12d035594f58db3eff215879e4ad8cf39b",
    "tailwindcss-linux-armv7": "704e7d91afba6e1f630889afd0d7db36b4634e628512cc141d504a5beae28860",
    "tailwindcss-linux-x64": "7d24f7fa191d2193b78cd5f5a42a6093e14409521908529f42d80b11fde1f1d4",
    "tailwindcss-macos-arm64": "a1d0c7985759accca0bf12e51ac1dcbf0f6cf2fffb62e6e0f62d091c477a10a3",
    "tailwindcss-macos-x64": "6cbdad74be776c087ffa5e9a057512c54898f9fe8828d3362212dfe32fc933a3",
    "tailwindcss-windows-arm64.exe": "76f516476784c00f1562160b5758e3d8f0e6c48957efb26b5b50fbdfd76aa382",
    "tailwindcss-windows-x64.exe": "67f1c5e3f5a03406a7bf5badf5ada09b79f3ae78ec43450c15f7e983068da346",
}


def get_binary_target():
    """Determina el nombre del binario standalone de Tailwind según el SO y arquitectura."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "linux":
        os_name = "linux"
    elif system == "darwin":
        os_name = "macos"
    elif system == "windows":
        os_name = "windows"
    else:
        raise CommandError(f"Sistema operativo no soportado: {system}")

    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        raise CommandError(f"Arquitectura no soportada: {machine}")

    ext = ".exe" if os_name == "windows" else ""
    return f"tailwindcss-{os_name}-{arch}{ext}"


def ensure_binary(bin_dir: pathlib.Path, stdout=None) -> pathlib.Path:
    """Descarga el binario standalone de Tailwind CLI si no existe en bin_dir."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    binary_name = get_binary_target()
    binary_path = bin_dir / f"tailwindcss{'.exe' if binary_name.endswith('.exe') else ''}"

    if binary_path.exists() and os.access(binary_path, os.X_OK):
        return binary_path

    url = (
        f"https://github.com/tailwindlabs/tailwindcss/releases/download/"
        f"v{TAILWIND_VERSION}/{binary_name}"
    )

    if stdout:
        stdout.write(f"Descargando Tailwind standalone CLI v{TAILWIND_VERSION} ({binary_name})...")

    req = urllib.request.Request(url, headers={"User-Agent": "ilovevoley-tailwind-cli"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        expected_sha = TAILWIND_SHA256.get(binary_name)
        if expected_sha:
            computed_sha = hashlib.sha256(data).hexdigest()
            if computed_sha != expected_sha:
                raise CommandError(
                    f"Checksum SHA256 no coincide para {binary_name}. "
                    f"Esperado: {expected_sha}, obtenido: {computed_sha}"
                )

        with open(binary_path, "wb") as f:
            f.write(data)
    except Exception as e:
        if binary_path.exists():
            binary_path.unlink()
        raise CommandError(f"Error descargando Tailwind CLI desde {url}: {e}")

    binary_path.chmod(0o755)

    if stdout:
        stdout.write(f"Tailwind standalone CLI instalado en {binary_path}")

    return binary_path


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
        bin_dir = base_dir / ".bin"
        input_css = base_dir / "ilovevoley" / "static" / "css" / "input.css"
        output_css = base_dir / "ilovevoley" / "static" / "css" / "app.css"
        config_file = base_dir / "tailwind.config.js"

        binary_path = ensure_binary(bin_dir, stdout=self.stdout)

        action = options["action"]
        watch_mode = options["watch"] or action == "watch"

        if action == "download":
            self.stdout.write(self.style.SUCCESS("Binario descargado correctamente."))
            return

        if not input_css.exists():
            raise CommandError(f"No se encuentra el archivo de entrada CSS: {input_css}")

        output_css.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(binary_path),
            "-c",
            str(config_file),
            "-i",
            str(input_css),
            "-o",
            str(output_css),
        ]

        if not options["no_minify"] and not watch_mode:
            cmd.append("--minify")

        if watch_mode:
            cmd.append("--watch")
            self.stdout.write(self.style.NOTICE("Vigilando cambios en CSS y plantillas... (Ctrl+C para salir)"))
            try:
                subprocess.run(cmd, check=True)
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS("\nVigilancia de Tailwind detenida."))
        else:
            self.stdout.write("Compilando CSS de Tailwind...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise CommandError(f"Error compilando Tailwind CSS:\n{result.stderr}")

            file_size_kb = output_css.stat().st_size / 1024
            self.stdout.write(
                self.style.SUCCESS(
                    f"Tailwind CSS compilado con éxito en {output_css} ({file_size_kb:.1f} KB)"
                )
            )
