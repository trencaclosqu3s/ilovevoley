import re
from pathlib import Path
import pytest
from django.conf import settings
from django.urls import get_resolver


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
    base_dir = Path(settings.BASE_DIR) / 'videosvoley'
    
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
    base_dir = Path(settings.BASE_DIR) / 'videosvoley'
    
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
    """Comprueba que todos los links definidos en UNFOLD['SIDEBAR']['navigation'] se resuelven correctamente."""
    unfold_settings = getattr(settings, 'UNFOLD', {})
    sidebar = unfold_settings.get('SIDEBAR', {})
    navigation = sidebar.get('navigation', [])

    failures = []
    checked = 0
    for section in navigation:
        for item in section.get('items', []):
            link = item.get('link')
            checked += 1
            try:
                resolved_link = str(link)
                assert resolved_link, "El enlace resuelto no puede ser vacío"
            except Exception as e:
                failures.append(f"Sección '{section.get('title')}' -> '{item.get('title')}': {e}")

    assert checked >= 10, f"Se esperaban al menos 10 enlaces en la barra lateral de Unfold, se encontraron {checked}"
    assert not failures, f"Fallo al resolver enlaces de Unfold Admin:\n" + "\n".join(failures)


@pytest.mark.django_db
def test_admin_index_renders_for_superuser(client):
    """Verifica que la página principal del admin carga (código 200) para un superusuario."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    admin_user = User.objects.create_superuser('admin_sidebar_test', 'adm@example.com', 'secret123')
    client.force_login(admin_user)
    response = client.get(f"/{settings.ADMIN_URL}")
    assert response.status_code == 200

