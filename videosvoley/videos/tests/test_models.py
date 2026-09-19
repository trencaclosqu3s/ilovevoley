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


class MatchManagerTests(TestCase):
    """El manager por defecto oculta los partidos retirados. Regla no evidente."""

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            name='Liga', federation_id='LIG-M', season='2024-25',
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
            name='Principal', federation_id='L-M', season='2024-25',
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.inactiva = League.objects.create(
            name='Inactiva', federation_id='L-I', season='2024-25',
            is_active=False, visibility_type='main', is_our_team_related=True,
        )
        cls.ajena = League.objects.create(
            name='Ajena', federation_id='L-E', season='2024-25',
            is_active=True, visibility_type='external', is_our_team_related=False,
        )
        cls.historica = League.objects.create(
            name='Historica', federation_id='L-H', season='2019-20',
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
            name='Liga Regular', federation_id='L-R', season='2024-25',
        )
        cls.oro = League.objects.create(
            name='Liga Regular', federation_id='L-ORO', season='2024-25',
            parent_league=cls.regular, phase_name='Liguilla Oro', phase_order=1,
        )
        cls.plata = League.objects.create(
            name='Liga Regular', federation_id='L-PLA', season='2024-25',
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


