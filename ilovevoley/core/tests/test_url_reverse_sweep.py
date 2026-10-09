import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.test import RequestFactory
from django.urls import get_resolver, resolve


def _can_resolve(url_name: str) -> bool:
    """Comprueba si un nombre de URL o URL con namespace puede resolverse en el URLconf actual."""
    resolver = get_resolver()
    if ':' in url_name:
        parts = url_name.split(':')
        cur = resolver
        for part in parts[:-1]:
            if part not in cur.namespace_dict:
                return False
            cur = cur.namespace_dict[part][1]
        return parts[-1] in cur.reverse_dict
    return url_name in resolver.reverse_dict


def test_template_url_tags_can_resolve():
    """Barre todos los templates HTML y comprueba que cada {% url '...' %} se puede resolver."""
    url_re = re.compile(r'{%\s*url\s+[\'\"]([^\'\"]+)[\'\"]')
    base_dir = Path(settings.BASE_DIR) / 'ilovevoley'
    
    template_files = list(base_dir.glob('templates/**/*.html'))
    # También incluir templates dentro de cada app cuando se muden
    template_files.extend(base_dir.glob('*/templates/**/*.html'))
    
    failures = []
    checked = 0
    
    for template_path in template_files:
        content = template_path.read_text(encoding='utf-8')
        for match in url_re.finditer(content):
            url_name = match.group(1)
            checked += 1
            if not _can_resolve(url_name):
                failures.append(f"{template_path.relative_to(base_dir)}: '{url_name}' cannot be resolved")
                
    assert checked > 100, f"Se esperaban más de 100 referencias url en templates, se encontraron {checked}"
    assert not failures, f"Fallo al resolver URLs en templates:\n" + "\n".join(failures)


def test_python_reverse_calls_can_resolve():
    """Barre todo el código Python y comprueba que las llamadas reverse(...) y redirect(...) literales se resuelven."""
    rev_re = re.compile(r'(?:reverse|redirect)\s*\(\s*[\'\"]([^\'\"]+)[\'\"]')
    base_dir = Path(settings.BASE_DIR) / 'ilovevoley'
    
    py_files = [
        p for p in base_dir.glob('**/*.py')
        if 'migrations' not in str(p) and 'tests' not in str(p)
    ]
    
    failures = []
    checked = 0
    
    for py_path in py_files:
        content = py_path.read_text(encoding='utf-8')
        for match in rev_re.finditer(content):
            url_name = match.group(1)
            # Ignorar redirects a rutas absolutas ej. '/videos/'
            if url_name.startswith('/'):
                continue
            checked += 1
            if not _can_resolve(url_name):
                failures.append(f"{py_path.relative_to(base_dir)}: '{url_name}' cannot be resolved")
                
    assert checked >= 15, f"Se esperaban al menos 15 referencias literales a reverse/redirect, se encontraron {checked}"
    assert not failures, f"Fallo al resolver URLs en Python:\n" + "\n".join(failures)


def test_unfold_sidebar_navigation_can_resolve():
    """Los enlaces de UNFOLD['SIDEBAR']['navigation'] deben resolver en el
    URLconf actual. Los ``reverse_lazy`` se materializan a su URL y cada
    destino se pasa por ``resolve()``; un enlace solo válido como texto
    (o roto) hace fallar el barrido."""
    unfold_settings = getattr(settings, 'UNFOLD', {})
    sidebar = unfold_settings.get('SIDEBAR', {})
    navigation = sidebar.get('navigation', [])

    failures = []
    checked = 0
    for section in navigation:
        for item in section.get('items', []):
            link = item.get('link')
            if link is None:
                continue
            checked += 1
            try:
                url = str(link)
                resolve(urlsplit(url).path)
            except Exception as e:
                failures.append(
                    f"Sección '{section.get('title')}' -> '{item.get('title')}': {e}"
                )

    assert checked >= 10, f"Se esperaban al menos 10 enlaces en la barra lateral de Unfold, se encontraron {checked}"
    assert not failures, f"Fallo al resolver enlaces de Unfold Admin:\n" + "\n".join(failures)


# Pares (ruta legada /videos/..., ruta canónica destino) de la issue #130.
LEGACY_VIDEOS_REDIRECTS = [
    # content
    ('/videos/', '/content/'),
    ('/videos/nuevo/', '/content/nuevo/'),
    ('/videos/nuevo-multiple/', '/content/nuevo-multiple/'),
    ('/videos/1/', '/content/1/'),
    ('/videos/imagenes/', '/content/imagenes/'),
    ('/videos/imagenes/individual/', '/content/imagenes/individual/'),
    ('/videos/imagenes/subir/', '/content/imagenes/subir/'),
    ('/videos/imagenes/subir-multiples/', '/content/imagenes/subir-multiples/'),
    ('/videos/imagenes/1/', '/content/imagenes/1/'),
    ('/videos/partidos/1/imagenes/', '/content/partidos/1/imagenes/'),
    (
        '/videos/imagenes/album/00000000-0000-0000-0000-000000000001/',
        '/content/imagenes/album/00000000-0000-0000-0000-000000000001/',
    ),
    ('/videos/admin/imagenes/moderar/', '/content/admin/imagenes/moderar/'),
    ('/videos/admin/imagenes/1/moderar/', '/content/admin/imagenes/1/moderar/'),
    ('/videos/admin/imagenes/moderar-masivo/', '/content/admin/imagenes/moderar-masivo/'),
    ('/videos/api/images/1/moderate/', '/content/api/images/1/moderate/'),
    # competitions
    ('/videos/ligas/', '/competitions/ligas/'),
    ('/videos/ligas/1/', '/competitions/ligas/1/'),
    ('/videos/partidos/1/', '/competitions/partidos/1/'),
    ('/videos/calendario/', '/competitions/calendario/'),
    ('/videos/clasificacion/', '/competitions/clasificacion/'),
    ('/videos/calendario/amistoso/nuevo/', '/competitions/calendario/amistoso/nuevo/'),
    (
        '/videos/calendario/suscripcion/token-abc/',
        '/competitions/calendario/suscripcion/token-abc/',
    ),
    ('/videos/ajax/matches-by-category/', '/competitions/ajax/matches-by-category/'),
    (
        '/videos/ajax/teams-by-league-category/',
        '/competitions/ajax/teams-by-league-category/',
    ),
    ('/videos/ajax/search-teams/', '/competitions/ajax/search-teams/'),
    ('/videos/ajax/partidos/1/resultado/', '/competitions/ajax/partidos/1/resultado/'),
    ('/videos/ajax/partidos/1/alineacion/', '/competitions/ajax/partidos/1/alineacion/'),
    # teams
    ('/videos/equipos/', '/teams/equipos/'),
    ('/videos/equipos/1/plantilla/', '/teams/equipos/1/plantilla/'),
    ('/videos/ajax/register-team/', '/teams/ajax/register-team/'),
    # rosters
    ('/videos/plantillas/', '/rosters/plantillas/'),
    ('/videos/personas/', '/rosters/personas/'),
    ('/videos/personas/nueva/', '/rosters/personas/nueva/'),
    ('/videos/personas/1/', '/rosters/personas/1/'),
    ('/videos/personas/1/editar/', '/rosters/personas/1/editar/'),
    ('/videos/personas/1/jugador/agregar/', '/rosters/personas/1/jugador/agregar/'),
    ('/videos/roles-jugador/1/editar/', '/rosters/roles-jugador/1/editar/'),
    ('/videos/roles-jugador/1/toggle/', '/rosters/roles-jugador/1/toggle/'),
    ('/videos/personas/1/staff/agregar/', '/rosters/personas/1/staff/agregar/'),
    ('/videos/roles-staff/1/editar/', '/rosters/roles-staff/1/editar/'),
    ('/videos/roles-staff/1/toggle/', '/rosters/roles-staff/1/toggle/'),
    # core
    ('/videos/moderacion/', '/core/moderacion/'),
    ('/videos/api/moderation/counts/', '/core/api/moderation/counts/'),
    ('/videos/api/users/1/approve/', '/core/api/users/1/approve/'),
    ('/videos/api/users/1/reject/', '/core/api/users/1/reject/'),
    ('/videos/quienes-somos/', '/core/quienes-somos/'),
    ('/videos/privacidad/', '/core/privacidad/'),
]


@pytest.mark.parametrize('legacy_path, canonical_path', LEGACY_VIDEOS_REDIRECTS)
def test_legacy_videos_urls_redirect_permanently(legacy_path, canonical_path):
    """Cada ruta legada de ``/videos/`` responde 301 hacia su ruta canónica (#130)."""
    match = resolve(legacy_path)
    request = RequestFactory().get(legacy_path)
    response = match.func(request, *match.args, **match.kwargs)

    assert response.status_code == 301, legacy_path
    assert response.url == canonical_path, legacy_path


def test_no_legacy_namespace_references():
    """Criterio #130: ninguna plantilla, script o test usa el namespace legado."""
    legacy_namespace = 'videos' + ':'
    base_dir = Path(settings.BASE_DIR) / 'ilovevoley'
    files = (
        list(base_dir.glob('**/*.html'))
        + list(base_dir.glob('**/*.js'))
        + [p for p in base_dir.glob('**/*.py') if 'migrations' not in str(p)]
    )

    offenders = [
        str(path.relative_to(base_dir))
        for path in files
        if legacy_namespace in path.read_text(encoding='utf-8')
    ]

    assert not offenders, f"Referencias al namespace legado en: {offenders}"

