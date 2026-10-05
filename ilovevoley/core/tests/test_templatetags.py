import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from ilovevoley.core.templatetags.icons import ICONS

ICON_TAG = re.compile(r"\{%\s*icon\s+['\"]([\w-]+)['\"]")


class IconTemplateTagTests(SimpleTestCase):
    def test_every_icon_used_in_templates_exists(self):
        """Un nombre mal escrito en {% icon %} solo explota (KeyError) al renderizar esa página, no al arrancar."""
        used = {}
        for path in Path(settings.BASE_DIR, 'ilovevoley').rglob('*.html'):
            for name in ICON_TAG.findall(path.read_text(encoding='utf-8')):
                used.setdefault(name, path.name)
        missing = {name: where for name, where in used.items() if name not in ICONS}
        self.assertEqual(missing, {})
