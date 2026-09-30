import os
from django.conf import settings
from django.test import TestCase
from PIL import Image


class PWAIconsTest(TestCase):
    def test_icons_exist_with_correct_dimensions(self):
        icons_dir = os.path.join(settings.BASE_DIR, 'ilovevoley', 'static', 'images', 'icons')
        expected_icons = {
            'icon-192.png': (192, 192),
            'icon-512.png': (512, 512),
            'icon-maskable-512.png': (512, 512),
            'apple-touch-icon-180.png': (180, 180),
        }
        for icon_name, (width, height) in expected_icons.items():
            path = os.path.join(icons_dir, icon_name)
            self.assertTrue(os.path.exists(path), f"Falta el icono {icon_name}")
            with Image.open(path) as img:
                self.assertEqual(img.size, (width, height), f"Dimensiones incorrectas para {icon_name}")
                self.assertEqual(img.format, 'PNG', f"El icono {icon_name} debe ser PNG")
