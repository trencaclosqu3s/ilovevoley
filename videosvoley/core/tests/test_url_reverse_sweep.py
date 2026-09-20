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
