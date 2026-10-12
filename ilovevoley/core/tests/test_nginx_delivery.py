import json
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import override_settings


def test_manifest_storage_falls_back_when_not_in_manifest():
    """Verifica que si un archivo no está en el manifiesto, devuelve la URL original sin lanzar error."""
    from django.contrib.staticfiles.storage import staticfiles_storage

    with tempfile.TemporaryDirectory() as tmp_dir:
        with override_settings(STATIC_ROOT=tmp_dir):
            # Manifest vacío / ausente: no debe lanzar ValueError
            url = staticfiles_storage.url("images/logo_app.png")
            assert url == "/static/images/logo_app.png"


def test_manifest_storage_hashes_static_files():
    """Verifica que collectstatic genera nombres con hash y crea el archivo staticfiles.json."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with override_settings(STATIC_ROOT=tmp_dir):
            call_command("collectstatic", interactive=False, verbosity=0)

            manifest_path = Path(tmp_dir) / "staticfiles.json"
            assert manifest_path.exists(), "El manifiesto staticfiles.json no fue generado"

            with open(manifest_path, encoding="utf-8") as f:
                manifest_data = json.load(f)

            paths = manifest_data.get("paths", {})
            assert "images/logo.svg" in paths
            assert "js/dark_mode.js" in paths

            # Los hashes de Django son de 12 caracteres hexadecimales
            hashed_logo = paths["images/logo.svg"]
            assert re.search(r"images/logo\.[0-9a-f]{12}\.svg", hashed_logo)

            hashed_file_on_disk = Path(tmp_dir) / hashed_logo
            assert hashed_file_on_disk.exists(), f"El archivo versionado {hashed_logo} no existe en disco"


def _get_server_blocks(content: str):
    """Devuelve los bloques server de nginx respetando llaves anidadas."""
    blocks = []
    idx = 0
    while True:
        pos = content.find("server {", idx)
        if pos == -1:
            break
        brace_count = 0
        end = -1
        for i in range(pos, len(content)):
            if content[i] == "{":
                brace_count += 1
            elif content[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        if end != -1:
            blocks.append(content[pos:end])
            idx = end
        else:
            break
    return blocks


def _get_ssl_server_for_host(servers, hostname: str):
    """Devuelve el primer bloque server SSL de contenido (con location) cuyo server_name incluye hostname."""
    for block in servers:
        if "listen 443 ssl" not in block or "location" not in block:
            continue
        match = re.search(r"server_name\s+([^;]+);", block)
        if match and hostname in match.group(1).split():
            return block
    return None


def test_nginx_conf_static_cache_control_and_immutability():
    """Verifica que no hay cabeceras Cache-Control duplicadas y que solo los archivos con hash son immutable."""
    nginx_conf_path = Path(settings.BASE_DIR) / "nginx.conf"
    content = nginx_conf_path.read_text(encoding="utf-8")

    servers = _get_server_blocks(content)
    ilovevoley_ssl = _get_ssl_server_for_host(servers, "ilovevoley.es")
    assert ilovevoley_ssl is not None, "Bloque server SSL para ilovevoley.es no encontrado"

    assert "location /static/" in ilovevoley_ssl

    # Extraer el bloque location /static/ respetando llaves
    pos = ilovevoley_ssl.find("location /static/")
    brace_count = 0
    end = -1
    for i in range(pos, len(ilovevoley_ssl)):
        if ilovevoley_ssl[i] == "{":
            brace_count += 1
        elif ilovevoley_ssl[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    assert end != -1, "No se pudo cerrar el bloque location /static/"
    static_block = ilovevoley_ssl[pos:end]

    # NO debe existir expires 30d junto a add_header Cache-Control (causa cabecera duplicada)
    assert "expires 30d;" not in static_block, (
        "expires 30d; no debe combinarse con add_header Cache-Control para evitar cabecera duplicada"
    )

    # Debe contener la regla para archivos con hash de 12 caracteres hex con immutable y 30 días
    assert re.search(r"\[0-9a-f\]\{12\}", static_block), (
        "No se detecta regla regex para archivos con hash de 12 caracteres hex"
    )
    assert "immutable" in static_block
    assert "max-age=2592000" in static_block


def test_nginx_serves_themed_error_pages_without_backend():
    """El rate limit y las caídas de backend muestran páginas propias, no las de nginx.

    Los errores que genera nginx (limit_req y 502/503/504) no pasan por Django, así
    que se sirven desde /static/ para que funcionen aunque gunicorn esté saturado o
    caído. El 429 además deja claro que es rate limiting y no una avería.
    """
    nginx_conf_path = Path(settings.BASE_DIR) / "nginx.conf"
    content = nginx_conf_path.read_text(encoding="utf-8")

    assert re.search(r"limit_req_status\s+429;", content), (
        "limit_req_status 429; no está configurado: el rate limit se confundiría con un 503"
    )

    servers = _get_server_blocks(content)
    ilovevoley_ssl = _get_ssl_server_for_host(servers, "ilovevoley.es")
    assert ilovevoley_ssl is not None, "Bloque server SSL para ilovevoley.es no encontrado"

    expected = {
        "429": "/static/errors/429.html",
        "502 503 504": "/static/errors/503.html",
    }
    static_dir = Path(settings.BASE_DIR) / "ilovevoley" / "static"
    for codes, path in expected.items():
        assert f"error_page {codes} {path};" in ilovevoley_ssl, (
            f"Falta error_page {codes} -> {path} en el server de ilovevoley.es"
        )
        static_file = static_dir / path.removeprefix("/static/")
        assert static_file.exists(), f"No existe la página de error estática {static_file}"

