from django.test import TestCase

from ilovevoley.core.models import Category
from ilovevoley.teams.models import Team
from ilovevoley.teams.utils import (
    find_duplicate_team_by_name,
    find_similar_team_by_name,
    normalize_team_name,
)
from ilovevoley.videos import utils as videos_utils


class NormalizeTeamNameTests(TestCase):
    """Verifica la transformación no trivial de nombres de equipos (#605)."""

    def test_normalize_empty_or_none(self):
        self.assertEqual(normalize_team_name(''), '')
        self.assertEqual(normalize_team_name(None), '')

    def test_normalize_html_entities(self):
        self.assertEqual(normalize_team_name("L&#39;Illa Grau"), "L'ILLA GRAU")
        self.assertEqual(normalize_team_name("L#39;Illa Grau"), "L'ILLA GRAU")
        self.assertEqual(normalize_team_name("CV &quot;Palma&quot;"), 'CV PALMA')
        self.assertEqual(normalize_team_name("A &amp; B"), 'A B')
        self.assertEqual(normalize_team_name("Sant&nbsp;Josep"), 'SANT JOSEP')

    def test_normalize_accents_and_casing(self):
        self.assertEqual(normalize_team_name("Voleibol Sóller"), "VOLEIBOL SOLLER")
        self.assertEqual(normalize_team_name("Club Barça"), "CLUB BARCA")

    def test_normalize_preserves_hyphen_and_apostrophe(self):
        self.assertEqual(normalize_team_name("Sant-Josep Obrer"), "SANT-JOSEP OBRER")
        self.assertEqual(normalize_team_name("L'Illa"), "L'ILLA")

    def test_normalize_strips_special_characters_and_extra_whitespace(self):
        self.assertEqual(normalize_team_name("  CV.  Sant   Josep!  "), "CV SANT JOSEP")


class FindDuplicateTeamTests(TestCase):
    """Verifica la resolución de duplicados por nombre normalizado (#605)."""

    @classmethod
    def setUpTestData(cls):
        cls.category_cadete = Category.objects.create(name='Cadete Femenino')
        cls.category_juvenil = Category.objects.create(name='Juvenil Femenino')
        cls.team = Team.objects.create(
            name="CV Sant Josep",
            category=cls.category_cadete,
            federation_id='SJ-01',
            is_active=True,
        )

    def test_find_duplicate_matches_normalized_name(self):
        # Mismo nombre con distinta capitalización y espaciado
        duplicate = find_duplicate_team_by_name("  cv   sant   josep  ")
        self.assertEqual(duplicate, self.team)

    def test_find_duplicate_respects_category(self):
        # En la misma categoría lo encuentra
        self.assertEqual(
            find_duplicate_team_by_name("cv sant josep", category=self.category_cadete),
            self.team,
        )
        # En otra categoría no coincide
        self.assertIsNone(
            find_duplicate_team_by_name("cv sant josep", category=self.category_juvenil)
        )

    def test_find_duplicate_respects_exclude_id(self):
        self.assertIsNone(
            find_duplicate_team_by_name("cv sant josep", exclude_id=self.team.id)
        )


class FindSimilarTeamTests(TestCase):
    """Verifica búsqueda por similitud difusa (#605)."""

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Senior Masculino')
        cls.team = Team.objects.create(
            name="Club Voleibol Manacor",
            category=cls.category,
            federation_id='MAN-01',
            is_active=True,
        )

    def test_find_similar_team_above_threshold(self):
        # Typo leve o ligera variación
        matched_team, score = find_similar_team_by_name(
            "Club Voleibol Manacorr",
            category=self.category,
            threshold=0.85,
        )
        self.assertEqual(matched_team, self.team)
        self.assertGreaterEqual(score, 0.85)

    def test_find_similar_team_below_threshold(self):
        matched_team, score = find_similar_team_by_name(
            "Club Voleibol Eivissa",
            category=self.category,
            threshold=0.85,
        )
        self.assertIsNone(matched_team)
        self.assertEqual(score, 0)


class VideoUtilsShimTests(TestCase):
    """Verifica que videos.utils mantiene compatibilidad regresiva (#605)."""

    def test_shims_point_to_teams_utils(self):
        self.assertIs(videos_utils.normalize_team_name, normalize_team_name)
        self.assertIs(videos_utils.find_duplicate_team_by_name, find_duplicate_team_by_name)
        self.assertIs(videos_utils.find_similar_team_by_name, find_similar_team_by_name)
