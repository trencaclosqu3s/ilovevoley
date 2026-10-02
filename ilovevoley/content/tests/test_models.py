from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image, Video
from ilovevoley.core.models import Category, Season
from ilovevoley.teams.models import Team

User = get_user_model()


TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class VideoSetNumberAndYoutubeIdTest(TestCase):
    def test_get_video_id_parses_watch_and_short_urls(self):
        self.assertEqual(
            Video(youtube_url='https://www.youtube.com/watch?v=XYZ789').get_video_id(),
            'XYZ789',
        )
        self.assertEqual(
            Video(youtube_url='https://youtu.be/XYZ789?t=3').get_video_id(),
            'XYZ789',
        )

    def test_get_thumbnail_url_uses_video_id(self):
        video = Video(youtube_url='https://www.youtube.com/watch?v=XYZ789')
        self.assertEqual(
            video.get_thumbnail_url(),
            'https://i.ytimg.com/vi/XYZ789/hqdefault.jpg',
        )

    def test_get_thumbnail_url_returns_none_for_unknown_url(self):
        self.assertIsNone(Video(youtube_url='https://example.com/x').get_thumbnail_url())


class SetNumberRequiresMatchTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u', password='p')
        self.match = Match.objects.create(match_date=timezone.now())

    def test_video_set_number_nulled_without_match(self):
        video = Video.objects.create(
            title='Sin partido',
            youtube_url='https://youtu.be/abc',
            set_number=2,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertIsNone(video.set_number)

    def test_video_set_number_persists_with_match(self):
        video = Video.objects.create(
            title='Con partido',
            youtube_url='https://youtu.be/abc',
            match=self.match,
            set_number=2,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertEqual(video.set_number, 2)

    def test_image_set_number_nulled_without_match(self):
        image = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Sin partido',
            set_number=3,
            uploaded_by=self.user,
        )
        image.refresh_from_db()
        self.assertIsNone(image.set_number)

    def test_image_set_number_persists_with_match(self):
        image = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Con partido',
            match=self.match,
            set_number=3,
            uploaded_by=self.user,
        )
        image.refresh_from_db()
        self.assertEqual(image.set_number, 3)


class VideoCategoryInheritanceTest(TestCase):
    """Un vídeo sin categoría explícita hereda la del partido al que se adjunta.

    Si no lo hiciera, quedaría con ``category=None`` y los filtros por categorías
    preferidas del usuario lo ocultarían del listado general.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u', password='p')

    def test_hereda_categoria_del_equipo_local(self):
        category = Category.objects.create(name='Infantil')
        home = Team.objects.create(name='Local', federation_id='TC-H', category=category)
        away = Team.objects.create(name='Visitante', federation_id='TC-A')
        match = Match.objects.create(match_date=timezone.now(), home_team=home, away_team=away)

        video = Video.objects.create(
            title='Con partido',
            youtube_url='https://youtu.be/abc',
            match=match,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertEqual(video.category, category)

    def test_hereda_categoria_de_la_liga_si_los_equipos_no_la_tienen(self):
        category = Category.objects.create(name='Cadete')
        league = League.objects.create(name='Liga Cadete', federation_id='TC-L')
        league.categories.add(category)
        match = Match.objects.create(match_date=timezone.now(), league=league)

        video = Video.objects.create(
            title='Con liga',
            youtube_url='https://youtu.be/abc',
            match=match,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertEqual(video.category, category)

    def test_respeta_la_categoria_explicita(self):
        match_category = Category.objects.create(name='Infantil')
        chosen = Category.objects.create(name='Alevín')
        home = Team.objects.create(name='Local', federation_id='TC-H', category=match_category)
        match = Match.objects.create(match_date=timezone.now(), home_team=home)

        video = Video.objects.create(
            title='Categoría elegida',
            youtube_url='https://youtu.be/abc',
            match=match,
            category=chosen,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertEqual(video.category, chosen)

    def test_sin_partido_la_categoria_queda_vacia(self):
        video = Video.objects.create(
            title='Suelto',
            youtube_url='https://youtu.be/abc',
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertIsNone(video.category)


class ImageSaveTests(TestCase):
    """Protege la lógica de Image.save(), invisible desde fuera del modelo."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='paula', password='x')
        cls.cat_liga = Category.objects.create(name='Cadete Femenino')
        cls.cat_local = Category.objects.create(name='Senior Femenino')
        cls.cat_visitante = Category.objects.create(name='Juvenil Femenino')
        cls.league = League.objects.create(
            name='Liga Balear', federation_id='LIG-1', season=Season.objects.resolve('2024-25'),
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

    def test_season_se_toma_de_la_liga_del_partido(self):
        imagen = self._crear_imagen(match=self.match)
        self.assertEqual(imagen.season.name, '2024-25')

    def test_season_sin_partido_se_infiere_de_la_fecha(self):
        imagen = self._crear_imagen()
        self.assertEqual(imagen.season, Season.objects.for_date(timezone.now()))

    def test_season_explicita_se_respeta_aunque_haya_partido(self):
        season = Season.objects.resolve('2020-21')
        imagen = self._crear_imagen(match=self.match, season=season)
        self.assertEqual(imagen.season, season)

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


class VideoSaveTests(TestCase):
    """Video.save() infiere la temporada del partido o de la fecha de subida."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='video-user', password='x')
        cls.league = League.objects.create(
            name='Liga Video', federation_id='LIG-V', season=Season.objects.resolve('2024-25'),
        )
        cls.team_a = Team.objects.create(name='VA', federation_id='TV-A')
        cls.team_b = Team.objects.create(name='VB', federation_id='TV-B')
        cls.match = Match.objects.create(
            league=cls.league, home_team=cls.team_a, away_team=cls.team_b,
            match_date=datetime(2024, 11, 3, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MV-1',
        )

    def _crear(self, **kwargs):
        kwargs.setdefault('title', 'Video')
        kwargs.setdefault('youtube_url', 'https://youtu.be/x')
        kwargs.setdefault('created_by', self.user)
        return Video.objects.create(**kwargs)

    def test_season_se_toma_del_partido(self):
        video = self._crear(match=self.match)
        self.assertEqual(video.season.name, '2024-25')

    def test_season_sin_partido_se_infiere_de_la_fecha(self):
        video = self._crear()
        self.assertEqual(video.season, Season.objects.for_date(timezone.now()))

    def test_season_explicita_se_respeta(self):
        season = Season.objects.resolve('2020-21')
        video = self._crear(season=season)
        self.assertEqual(video.season, season)


class VideoEmbedUrlTests(TestCase):
    """Parsing de tres formatos de URL de YouTube hacia el dominio nocookie."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='bert', password='x')

    def _video(self, url):
        return Video.objects.create(
            title='Partido', youtube_url=url, created_by=self.user
        )

    def _esperado(self, video_id):
        return (
            f'https://www.youtube-nocookie.com/embed/{video_id}'
            '?rel=0&modestbranding=1&fs=1&enablejsapi=0'
        )

    def test_url_watch_se_convierte_en_embed_nocookie(self):
        video = self._video('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(video.get_embed_url(), self._esperado('dQw4w9WgXcQ'))

    def test_url_watch_con_parametros_extra_ignora_la_cola(self):
        video = self._video('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s')
        self.assertEqual(video.get_embed_url(), self._esperado('dQw4w9WgXcQ'))

    def test_url_corta_youtu_be(self):
        video = self._video('https://youtu.be/dQw4w9WgXcQ')
        self.assertEqual(video.get_embed_url(), self._esperado('dQw4w9WgXcQ'))

    def test_url_de_directo(self):
        video = self._video('https://www.youtube.com/live/AbCdEf12345')
        self.assertEqual(video.get_embed_url(), self._esperado('AbCdEf12345'))

    def test_url_no_reconocida_se_devuelve_intacta(self):
        video = self._video('https://vimeo.com/123456')
        self.assertEqual(video.get_embed_url(), 'https://vimeo.com/123456')

    def test_is_livestream_detecta_los_directos(self):
        self.assertTrue(self._video('https://www.youtube.com/live/AbC').is_livestream())
        self.assertFalse(
            self._video('https://www.youtube.com/watch?v=AbC').is_livestream()
        )

    def test_get_video_type_distingue_directo_de_video(self):
        self.assertEqual(
            self._video('https://www.youtube.com/live/AbC').get_video_type(),
            'livestream',
        )
        self.assertEqual(
            self._video('https://www.youtube.com/watch?v=AbC').get_video_type(),
            'video',
        )
