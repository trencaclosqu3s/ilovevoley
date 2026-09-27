import re
from pathlib import Path
from django.conf import settings


def test_docker_compose_web_gunicorn_flags():
    """Verifica que el servicio web en docker-compose.yml tiene configurado el reciclado de workers y flags de resiliencia."""
    compose_path = Path(settings.BASE_DIR) / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml no encontrado en la raíz del proyecto"

    content = compose_path.read_text(encoding="utf-8")

    # Extraer bloque del servicio web
    web_match = re.search(r'web:\s*\n((?:\s+.*\n)+)', content)
    assert web_match is not None, "Servicio web no encontrado en docker-compose.yml"

    web_block = web_match.group(1)
    command_match = re.search(r'command:\s*(.+)', web_block)
    assert command_match is not None, "command no encontrado en servicio web de docker-compose.yml"

    command = command_match.group(1)
    assert "gunicorn" in command, "El comando del servicio web no invoca gunicorn"
    assert "--max-requests 1000" in command, "--max-requests 1000 ausente en command de web"
    assert "--max-requests-jitter 100" in command, "--max-requests-jitter 100 ausente en command de web"
    assert "--timeout 30" in command, "--timeout 30 ausente en command de web"
    assert "--access-logfile -" in command, "--access-logfile - ausente en command de web"


def test_dockerfile_gunicorn_cmd_flags():
    """Verifica que el CMD por defecto en Dockerfile incluye reciclado de workers y flags de resiliencia."""
    dockerfile_path = Path(settings.BASE_DIR) / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile no encontrado en la raíz del proyecto"

    content = dockerfile_path.read_text(encoding="utf-8")
    cmd_match = re.search(r'CMD\s*\[(.*?)\]', content)
    assert cmd_match is not None, "CMD no encontrado en Dockerfile"

    cmd_str = cmd_match.group(1)
    assert '"--max-requests"' in cmd_str and '"1000"' in cmd_str, "--max-requests 1000 ausente en CMD de Dockerfile"
    assert '"--max-requests-jitter"' in cmd_str and '"100"' in cmd_str, "--max-requests-jitter 100 ausente en CMD de Dockerfile"
    assert '"--timeout"' in cmd_str and '"30"' in cmd_str, "--timeout 30 ausente en CMD de Dockerfile"
    assert '"--access-logfile"' in cmd_str and '"-"' in cmd_str, "--access-logfile - ausente en CMD de Dockerfile"


def test_dockerfile_variants_gunicorn_cmd_flags():
    """Verifica que las variantes Dockerfile.alpine y Dockerfile.rag incluyen los flags requeridos en su CMD."""
    variants = ["Dockerfile.alpine", "Dockerfile.rag"]
    for filename in variants:
        variant_path = Path(settings.BASE_DIR) / filename
        if not variant_path.exists():
            continue

        content = variant_path.read_text(encoding="utf-8")
        cmd_match = re.search(r'CMD\s*\[(.*?)\]', content)
        assert cmd_match is not None, f"CMD no encontrado en {filename}"

        cmd_str = cmd_match.group(1)
        assert '"--max-requests"' in cmd_str and '"1000"' in cmd_str, f"--max-requests 1000 ausente en CMD de {filename}"
        assert '"--max-requests-jitter"' in cmd_str and '"100"' in cmd_str, f"--max-requests-jitter 100 ausente en CMD de {filename}"
        assert '"--timeout"' in cmd_str and '"30"' in cmd_str, f"--timeout 30 ausente en CMD de {filename}"
        assert '"--access-logfile"' in cmd_str and '"-"' in cmd_str, f"--access-logfile - ausente en CMD de {filename}"
