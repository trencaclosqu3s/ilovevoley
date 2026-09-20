from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from videosvoley.core.models import Season
from videosvoley.videos.models import Category, Image, League, Match, Team, Video

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


class MatchManagerTests(TestCase):
    """El manager por defecto oculta los partidos retirados. Regla no evidente."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='LIG-M', season=Season.objects.resolve('2024-25'),
        )
        cls.a = Team.objects.create(name='A', federation_id='T-A')
        cls.b = Team.objects.create(name='B', federation_id='T-B')
        cls.jugado = Match.objects.create(
            league=cls.league, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 11, 3, 12, 0, tzinfo=dt_timezone.utc),
            status='finished', federation_id='M-OK',
        )
        cls.retirado = Match.objects.create(
            league=cls.league, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 11, 10, 12, 0, tzinfo=dt_timezone.utc),
            status='withdrawn', federation_id='M-W',
        )

    def test_manager_por_defecto_oculta_los_retirados(self):
        self.assertEqual(list(Match.objects.all()), [self.jugado])

    def test_all_objects_incluye_los_retirados(self):
        self.assertEqual(Match.all_objects.count(), 2)

    def test_el_manager_por_defecto_es_el_que_filtra(self):
        # Match._default_manager es el que usan el admin y las relaciones.
        self.assertEqual(Match._default_manager.count(), 1)


class LeagueManagerTests(TestCase):
    """visible_in_app() exige tres condiciones a la vez, no una."""

    @classmethod
    def setUpTestData(cls):
        cls.principal = League.objects.create(
            name='Principal', federation_id='L-M', season=Season.objects.resolve('2024-25'),
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.inactiva = League.objects.create(
            name='Inactiva', federation_id='L-I', season=Season.objects.resolve('2024-25'),
            is_active=False, visibility_type='main', is_our_team_related=True,
        )
        cls.ajena = League.objects.create(
            name='Ajena', federation_id='L-E', season=Season.objects.resolve('2024-25'),
            is_active=True, visibility_type='external', is_our_team_related=False,
        )
        cls.historica = League.objects.create(
            name='Historica', federation_id='L-H', season=Season.objects.resolve('2019-20'),
            is_active=True, visibility_type='historical', is_historical=True,
        )

    def _nombres(self, queryset):
        return set(queryset.values_list('name', flat=True))

    def test_visible_in_app_solo_devuelve_la_que_cumple_las_tres_condiciones(self):
        self.assertEqual(self._nombres(League.objects.visible_in_app()), {'Principal'})

    def test_reference_leagues_agrupa_los_tres_tipos_no_principales(self):
        self.assertEqual(
            self._nombres(League.objects.reference_leagues()), {'Ajena', 'Historica'}
        )

    def test_historical_leagues_exige_el_flag_ademas_del_tipo(self):
        self.assertEqual(self._nombres(League.objects.historical_leagues()), {'Historica'})

    def test_external_leagues_exige_no_estar_relacionada_con_nuestro_equipo(self):
        self.assertEqual(self._nombres(League.objects.external_leagues()), {'Ajena'})


class LeaguePhaseTests(TestCase):
    """Fases de liga: la recursión sube al padre y agrega sus partidos."""

    @classmethod
    def setUpTestData(cls):
        cls.regular = League.objects.create(
            name='Liga Regular', federation_id='L-R', season=Season.objects.resolve('2024-25'),
        )
        cls.oro = League.objects.create(
            name='Liga Regular', federation_id='L-ORO', season=Season.objects.resolve('2024-25'),
            parent_league=cls.regular, phase_name='Liguilla Oro', phase_order=1,
        )
        cls.plata = League.objects.create(
            name='Liga Regular', federation_id='L-PLA', season=Season.objects.resolve('2024-25'),
            parent_league=cls.regular, phase_name='Liguilla Plata', phase_order=2,
        )
        cls.a = Team.objects.create(name='A', federation_id='TP-A')
        cls.b = Team.objects.create(name='B', federation_id='TP-B')
        cls.partido_regular = Match.objects.create(
            league=cls.regular, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2024, 10, 5, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MP-1',
        )
        cls.partido_oro = Match.objects.create(
            league=cls.oro, home_team=cls.a, away_team=cls.b,
            match_date=datetime(2025, 2, 8, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MP-2',
        )

    def test_is_phase_distingue_la_liga_raiz_de_sus_fases(self):
        self.assertFalse(self.regular.is_phase)
        self.assertTrue(self.oro.is_phase)

    def test_root_league_sube_hasta_la_raiz_desde_una_fase(self):
        self.assertEqual(self.oro.root_league, self.regular)

    def test_get_all_phases_devuelve_la_raiz_primero_y_luego_las_fases_ordenadas(self):
        self.assertEqual(
            self.regular.get_all_phases(), [self.regular, self.oro, self.plata]
        )

    def test_get_all_phases_desde_una_fase_devuelve_lo_mismo_que_desde_la_raiz(self):
        self.assertEqual(self.oro.get_all_phases(), self.regular.get_all_phases())

    def test_get_combined_matches_agrega_los_partidos_de_todas_las_fases(self):
        self.assertEqual(
            set(self.regular.get_combined_matches()),
            {self.partido_regular, self.partido_oro},
        )

    def test_get_combined_matches_desde_una_fase_agrega_igual(self):
        self.assertEqual(
            set(self.oro.get_combined_matches()),
            {self.partido_regular, self.partido_oro},
        )

    def test_display_name_prioriza_el_override_sobre_el_nombre_de_fase(self):
        self.oro.display_name_override = 'Fase de Oro 24/25'
        self.assertEqual(self.oro.display_name, 'Fase de Oro 24/25')

    def test_display_name_concatena_el_nombre_de_fase_si_no_hay_override(self):
        self.assertEqual(self.oro.display_name, 'Liga Regular - Liguilla Oro')


class TeamVariantTests(TestCase):
    """Variantes de equipo: misma recursión que las fases de liga."""

    @classmethod
    def setUpTestData(cls):
        cls.principal = Team.objects.create(name='Sant Josep', federation_id='TV-0')
        cls.groc = Team.objects.create(
            name='Sant Josep', federation_id='TV-1',
            parent_team=cls.principal, variant_type='color', variant_name='Groc',
        )
        cls.lila = Team.objects.create(
            name='Sant Josep', federation_id='TV-2',
            parent_team=cls.principal, variant_type='color', variant_name='Lila',
        )
        cls.retirado = Team.objects.create(
            name='Sant Josep', federation_id='TV-3',
            parent_team=cls.principal, variant_name='Blau', is_active=False,
        )

    def test_is_variant_distingue_el_equipo_principal_de_sus_variantes(self):
        self.assertFalse(self.principal.is_variant)
        self.assertTrue(self.groc.is_variant)

    def test_root_team_sube_hasta_el_equipo_principal(self):
        self.assertEqual(self.groc.root_team, self.principal)

    def test_get_all_variants_incluye_el_principal_y_excluye_las_inactivas(self):
        self.assertEqual(
            self.principal.get_all_variants(), [self.principal, self.groc, self.lila]
        )

    def test_get_all_variants_desde_una_variante_devuelve_lo_mismo(self):
        self.assertEqual(self.groc.get_all_variants(), self.principal.get_all_variants())

    def test_display_name_with_variant_anade_la_variante_entre_parentesis(self):
        self.assertEqual(self.groc.display_name_with_variant, 'Sant Josep (Groc)')

    def test_display_name_with_variant_no_anade_nada_al_principal(self):
        self.assertEqual(self.principal.display_name_with_variant, 'Sant Josep')


class MatchCleanTests(TestCase):
    """Validación propia de Match, que no cubre ningún validador de Django."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='L-C', season=Season.objects.resolve('2024-25'),
        )
        cls.a = Team.objects.create(name='A', federation_id='TC-A')
        cls.b = Team.objects.create(name='B', federation_id='TC-B')

    def test_un_amistoso_no_puede_llevar_federation_id(self):
        partido = Match(
            is_friendly=True,
            federation_id='F-1',
            home_team_text='Equipo invitado',
            away_team_text='Sant Josep',
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_ya_guardado_exige_equipo_local(self):
        partido = Match.objects.create(
            league=self.league, home_team=self.a, away_team=self.b,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MC-1',
        )
        partido.home_team = None
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_ya_guardado_exige_equipo_visitante(self):
        partido = Match.objects.create(
            league=self.league, home_team=self.a, away_team=self.b,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='MC-2',
        )
        partido.away_team = None
        with self.assertRaises(ValidationError):
            partido.clean()

    def test_un_partido_oficial_sin_guardar_no_exige_equipos(self):
        # La validación solo aplica si self.pk is not None: durante la creación
        # es el formulario quien valida.
        partido = Match(
            league=self.league,
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        partido.clean()  # no debe lanzar

    def test_un_amistoso_con_equipos_en_texto_es_valido(self):
        partido = Match(
            is_friendly=True,
            home_team_text='Equipo invitado',
            away_team_text='Sant Josep',
            match_date=datetime(2024, 12, 1, 12, 0, tzinfo=dt_timezone.utc),
        )
        partido.clean()  # no debe lanzar


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



