import json
import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.template import Context, Template
from django.test import override_settings


def test_storages_configured_with_manifest_static_files_storage():
    """Verifica que STORAGES tiene configurado ManifestStaticFilesStorage para staticfiles."""
    from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
    from django.utils.module_loading import import_string

    assert hasattr(settings, "STORAGES")
    assert "staticfiles" in settings.STORAGES
    backend_cls = import_string(settings.STORAGES["staticfiles"]["BACKEND"])
    assert issubclass(backend_cls, ManifestStaticFilesStorage)
    assert backend_cls.manifest_strict is False


def test_manifest_storage_falls_back_when_not_in_manifest():
    """Verifica que si un archivo no está en el manifiesto, devuelve la URL original sin lanzar error."""
    from django.contrib.staticfiles.storage import staticfiles_storage

    # Sin collectstatic previo, no debe lanzar ValueError
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


def test_static_template_tag_resolves_hashed_url_with_manifest():
    """Verifica que el tag {% static %} resuelve URLs con hash cuando existe manifiesto y DEBUG=False."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with override_settings(STATIC_ROOT=tmp_dir):
            call_command("collectstatic", interactive=False, verbosity=0)

            with override_settings(DEBUG=False):
                template = Template("{% load static %}{% static 'images/logo.svg' %}")
                rendered = template.render(Context())
                assert re.search(r"/static/images/logo\.[0-9a-f]{12}\.svg", rendered)


def test_nginx_conf_gzip_configuration():
    """Verifica que nginx.conf activa compresión gzip con los tipos MIME requeridos."""
    nginx_conf_path = Path(settings.BASE_DIR) / "nginx.conf"
    assert nginx_conf_path.exists(), "nginx.conf no encontrado en la raíz del proyecto"

    content = nginx_conf_path.read_text(encoding="utf-8")

    assert re.search(r"gzip\s+on;", content), "gzip on; no está activado en nginx.conf"
    assert re.search(r"gzip_vary\s+on;", content), "gzip_vary on; no está activado en nginx.conf"

    # Tipos requeridos por el alcance del issue #112
    required_types = [
        "text/css",
        "application/javascript",
        "application/json",
        "image/svg+xml",
    ]
    for mime_type in required_types:
        assert mime_type in content, f"Tipo MIME {mime_type} ausente en gzip_types de nginx.conf"


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


def test_nginx_conf_http2_configuration():
    """Verifica que HTTP/2 está habilitado para conexiones SSL en nginx.conf."""
    nginx_conf_path = Path(settings.BASE_DIR) / "nginx.conf"
    content = nginx_conf_path.read_text(encoding="utf-8")

    assert re.search(r"http2\s+on;", content), "Directiva 'http2 on;' no encontrada en nginx.conf"

    # Verificar que el bloque de servidor SSL ilovevoley.es incluye http2 on
    servers = _get_server_blocks(content)
    ssl_servers = [s for s in servers if "listen 443 ssl" in s]
    assert ssl_servers, "No se encontraron servidores escuchando en 443 ssl"

    ilovevoley_ssl = next(
        (s for s in ssl_servers if "ilovevoley.es" in s),
        None,
    )
    assert ilovevoley_ssl is not None, "Bloque server SSL para ilovevoley.es no encontrado"
    assert "http2 on;" in ilovevoley_ssl, "http2 on; no está en el bloque server SSL de ilovevoley.es"


def test_nginx_conf_static_cache_control_and_immutability():
    """Verifica que no hay cabeceras Cache-Control duplicadas y que solo los archivos con hash son immutable."""
    nginx_conf_path = Path(settings.BASE_DIR) / "nginx.conf"
    content = nginx_conf_path.read_text(encoding="utf-8")

    servers = _get_server_blocks(content)
    ilovevoley_ssl = next(
        (s for s in servers if "listen 443 ssl" in s and "ilovevoley.es" in s),
        None,
    )
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


def test_nginx_conf_all_ssl_servers_have_http2():
    """Verifica que todos los bloques de servidor con SSL tienen directiva http2 on;."""
    nginx_conf_path = Path(settings.BASE_DIR) / "nginx.conf"
    content = nginx_conf_path.read_text(encoding="utf-8")

    servers = _get_server_blocks(content)
    ssl_servers = [s for s in servers if "listen 443 ssl" in s]
    assert len(ssl_servers) >= 10, "Se esperaba encontrar los servidores SSL del archivo"
    for s in ssl_servers:
        assert "http2 on;" in s, f"Servidor SSL sin directiva 'http2 on;':\n{s[:120]}"

