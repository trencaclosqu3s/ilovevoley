from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from ilovevoley.core.models import GENDER_FEMALE, GENDER_MALE, Category
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.services import cache_logo


class TeamEffectiveGenderTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(federation_id='gender-club', official_name='Club Gender')

    def test_own_gender_wins_over_category(self):
        category = Category.objects.create(name='Senior M gender', gender=GENDER_MALE)
        team = Team.objects.create(
            name='Team Own', federation_id='gender-t1', club=self.club,
            category=category, gender=GENDER_FEMALE,
        )
        self.assertEqual(team.effective_gender, GENDER_FEMALE)

    def test_inherits_from_category_and_defaults_to_blank(self):
        category = Category.objects.create(name='Senior F gender', gender=GENDER_FEMALE)
        team = Team.objects.create(
            name='Team Inherit', federation_id='gender-t2', club=self.club, category=category,
        )
        self.assertEqual(team.effective_gender, GENDER_FEMALE)

        empty = Team.objects.create(name='Team Empty', federation_id='gender-t3', club=self.club)
        self.assertEqual(empty.effective_gender, '')


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


class DisplayLogoTests(SimpleTestCase):
    """Precedencia del escudo: copia local antes que la URL de la federación."""

    def test_local_copy_wins_over_remote_urls(self):
        club = Club(federation_id='7', logo='clubs/logos/7.png')
        team = Team(club=club)

        self.assertEqual(team.display_logo_file.name, 'clubs/logos/7.png')
        self.assertTrue(team.display_logo.endswith('clubs/logos/7.png'))

    def test_team_with_own_logo_url_does_not_inherit_club_local_copy(self):
        club = Club(federation_id='7', logo='clubs/logos/7.png')
        team = Team(club=club, logo_url='https://fed.example/team.jpg')

        self.assertIsNone(team.display_logo_file)
        self.assertEqual(team.display_logo, 'https://fed.example/team.jpg')

    def test_falls_back_to_federation_url_without_local_copy(self):
        club = Club(federation_id='7')

        self.assertIsNone(Team(club=club).display_logo_file)
        self.assertEqual(Team(club=club).display_logo, club.logo_federation_url)
        self.assertEqual(
            Team(club=club, logo_url='https://fed.example/team.jpg').display_logo,
            'https://fed.example/team.jpg',
        )


class CacheLogoTests(SimpleTestCase):
    @patch('ilovevoley.competitions.result_card.fetch_logo_bytes')
    def test_failed_download_or_invalid_image_leaves_logo_empty(self, fetch):
        club = Club(federation_id='7')
        for payload in (None, b'<html>no es una imagen</html>'):
            fetch.return_value = payload
            self.assertFalse(cache_logo(club))
            self.assertFalse(club.logo)
