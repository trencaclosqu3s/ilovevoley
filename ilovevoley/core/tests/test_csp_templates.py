import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / 'ilovevoley'

# Correo (no se sirve con CSP de página) y admin (política relajada por
# AdminCSPMiddleware: Unfold/Alpine necesitan inline/eval).
EXCLUDED_PARTS = ('/emails/', '/templates/admin/')

INLINE_HANDLER_RE = re.compile(
    r'\son(?:click|change|submit|load|error|input|keyup|keydown|focus|blur|'
    r'mouseover|mouseout|animationend|drop)\s*=\s*["\']'
)
STYLE_ATTR_RE = re.compile(r'\sstyle\s*=\s*["\']')
SCRIPT_WITHOUT_NONCE_RE = re.compile(r'<script(?![^>]*\bnonce=)(?![^>]*\bsrc=)[^>]*>')
STYLE_WITHOUT_NONCE_RE = re.compile(r'<style(?![^>]*\bnonce=)[^>]*>')


def _public_templates():
    for path in TEMPLATES_DIR.rglob('*.html'):
        posix = path.as_posix()
        if any(part in posix for part in EXCLUDED_PARTS):
            continue
        yield path


class CspTemplateAuditTest(SimpleTestCase):
    """Las plantillas públicas no deben romper la CSP estricta.

    Si alguno de estos tests falla, la página afectada perdería su
    comportamiento en producción (CSP enforce sin unsafe-inline).
    """

    def test_no_inline_event_handlers(self):
        offenders = []
        for path in _public_templates():
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if INLINE_HANDLER_RE.search(line):
                    offenders.append(f'{path.relative_to(TEMPLATES_DIR)}:{lineno}')
        self.assertEqual(offenders, [], f'Handlers inline encontrados: {offenders}')

    def test_no_inline_style_attributes(self):
        offenders = []
        for path in _public_templates():
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if STYLE_ATTR_RE.search(line):
                    offenders.append(f'{path.relative_to(TEMPLATES_DIR)}:{lineno}')
        self.assertEqual(offenders, [], f'Atributos style= encontrados: {offenders}')

    def test_inline_scripts_and_styles_carry_nonce(self):
        offenders = []
        for path in _public_templates():
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if SCRIPT_WITHOUT_NONCE_RE.search(line) or STYLE_WITHOUT_NONCE_RE.search(line):
                    offenders.append(f'{path.relative_to(TEMPLATES_DIR)}:{lineno}')
        self.assertEqual(offenders, [], f'Inline sin nonce encontrados: {offenders}')
