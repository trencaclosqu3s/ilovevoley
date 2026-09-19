from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from videosvoley.videos.models import Category, Image, League, Match, Team

User = get_user_model()

# GIF 1x1 real: evita depender de cómo trate Pillow unos bytes arbitrarios.
TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class ImageSaveTests(TestCase):
    """Protege la lógica de Image.save(), invisible desde fuera del modelo."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='paula', password='x')
        cls.cat_liga = Category.objects.create(name='Cadete Femenino')
        cls.cat_local = Category.objects.create(name='Senior Femenino')
        cls.cat_visitante = Category.objects.create(name='Juvenil Femenino')
        cls.league = League.objects.create(
            name='Liga Balear', federation_id='LIG-1', season='2024-25',
        )
        cls.league.categories.add(cls.cat_liga)
        cls.local = Team.objects.create(
            name='Sant Josep', federation_id='T-1', category=cls.cat_local,
        )
        cls.visitante = Team.objects.create(
            name='Manacor', federation_id='T-2', category=cls.cat_visitante,
        )
        cls.match = Match.objects.create(
            league=cls.league,
            home_team=cls.local,
            away_team=cls.visitante,
            match_date=datetime(2024, 11, 3, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='M-1',
        )

    def _crear_imagen(self, **kwargs):
        kwargs.setdefault('title', 'Saque de Paula')
        kwargs.setdefault('uploaded_by', self.user)
        kwargs.setdefault(
            'image',
            SimpleUploadedFile('punto.jpg', TINY_GIF, content_type='image/jpeg'),
        )
        return Image.objects.create(**kwargs)

    def test_year_se_toma_del_ano_del_partido(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(imagen.year, 2024)

    def test_year_sin_partido_usa_el_ano_actual(self):
        imagen = self._crear_imagen()
        self.assertEqual(imagen.year, timezone.now().year)

    def test_image_type_other_pasa_a_match_al_vincular_partido(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(imagen.image_type, 'match')

    def test_image_type_explicito_no_se_pisa(self):
        imagen = self._crear_imagen(match=self.match, image_type='celebration')
        self.assertEqual(imagen.image_type, 'celebration')

    def test_hereda_categorias_de_la_liga_y_de_ambos_equipos(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(
            set(imagen.categories.values_list('name', flat=True)),
            {'Cadete Femenino', 'Senior Femenino', 'Juvenil Femenino'},
        )

    def test_imagen_sin_partido_no_hereda_categorias(self):
        imagen = self._crear_imagen()
        self.assertEqual(imagen.categories.count(), 0)
