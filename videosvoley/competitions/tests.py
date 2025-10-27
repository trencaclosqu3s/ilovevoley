from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from .models import League, Match, Standing, ScrapingEndpoint

User = get_user_model()


class LeagueModelTest(TestCase):
    def setUp(self):
        self.league = League.objects.create(
            name="Liga Senior",
            federation_id="12345",
            competition_type="regular",
            season="2024-25",
            is_active=True,
            visibility_type="main"
        )

    def test_league_creation(self):
        self.assertEqual(self.league.name, "Liga Senior")
        self.assertEqual(self.league.federation_id, "12345")
        self.assertTrue(self.league.is_active)

    def test_league_str(self):
        expected = f"{self.league.name} ({self.league.season})"
        self.assertEqual(str(self.league), expected)

    def test_has_pending_matches(self):
        # Sin partidos, no debería tener partidos pendientes
        self.assertFalse(self.league.has_pending_matches)
        
        # Crear partido futuro
        future_date = timezone.now() + timezone.timedelta(days=1)
        Match.objects.create(
            league=self.league,
            home_team_text="Equipo A",
            away_team_text="Equipo B",
            match_date=future_date,
            status="scheduled"
        )
        self.assertTrue(self.league.has_pending_matches)

    def test_should_show_in_app(self):
        # Liga principal activa debería mostrarse
        self.assertTrue(self.league.should_show_in_app)
        
        # Liga de referencia no debería mostrarse
        self.league.visibility_type = "reference"
        self.assertFalse(self.league.should_show_in_app)

    def test_is_reference_league(self):
        # Liga principal no es de referencia
        self.assertFalse(self.league.is_reference_league)
        
        # Liga de referencia sí es de referencia
        self.league.visibility_type = "reference"
        self.assertTrue(self.league.is_reference_league)


class MatchModelTest(TestCase):
    def setUp(self):
        self.league = League.objects.create(
            name="Liga Test",
            federation_id="12345",
            season="2024-25"
        )
        self.match = Match.objects.create(
            league=self.league,
            home_team_text="Equipo Local",
            away_team_text="Equipo Visitante",
            match_date=timezone.now() + timezone.timedelta(days=1),
            status="scheduled"
        )

    def test_match_creation(self):
        self.assertEqual(self.match.home_team_text, "Equipo Local")
        self.assertEqual(self.match.away_team_text, "Equipo Visitante")
        self.assertEqual(self.match.league, self.league)

    def test_match_str(self):
        expected_date = self.match.match_date.strftime("%d/%m/%Y")
        expected = f"Equipo Local vs Equipo Visitante - {expected_date}"
        self.assertEqual(str(self.match), expected)

    def test_is_finished(self):
        self.assertFalse(self.match.is_finished)
        self.match.status = "finished"
        self.assertTrue(self.match.is_finished)

    def test_result_display(self):
        # Sin resultado
        self.assertEqual(self.match.result_display, "Sin resultado")
        
        # Con resultado
        self.match.home_score = 3
        self.match.away_score = 1
        self.assertEqual(self.match.result_display, "3 - 1")

    def test_home_team_display(self):
        self.assertEqual(self.match.home_team_display, "Equipo Local")
        
        # Sin equipo local
        self.match.home_team_text = ""
        self.assertEqual(self.match.home_team_display, "Equipo Local")

    def test_away_team_display(self):
        self.assertEqual(self.match.away_team_display, "Equipo Visitante")
        
        # Sin equipo visitante
        self.match.away_team_text = ""
        self.assertEqual(self.match.away_team_display, "Equipo Visitante")

    def test_is_official(self):
        # Partido amistoso no es oficial
        self.assertFalse(self.match.is_official)
        
        # Partido con federation_id es oficial
        self.match.federation_id = "match_123"
        self.match.is_friendly = False
        self.assertTrue(self.match.is_official)


class StandingModelTest(TestCase):
    def setUp(self):
        self.league = League.objects.create(
            name="Liga Test",
            federation_id="12345",
            season="2024-25"
        )
        # Nota: Este test fallará hasta que se cree la app teams
        # self.team = Team.objects.create(name="Equipo Test")
        # self.standing = Standing.objects.create(
        #     league=self.league,
        #     team=self.team,
        #     position=1,
        #     played=10,
        #     won=8,
        #     lost=2,
        #     total_points=24
        # )

    def test_standing_creation(self):
        # Este test se completará cuando se cree la app teams
        pass

    def test_set_difference(self):
        # Este test se completará cuando se cree la app teams
        pass

    def test_win_percentage(self):
        # Este test se completará cuando se cree la app teams
        pass


class ScrapingEndpointModelTest(TestCase):
    def setUp(self):
        self.league = League.objects.create(
            name="Liga Test",
            federation_id="12345",
            season="2024-25"
        )
        self.endpoint = ScrapingEndpoint.objects.create(
            league=self.league,
            endpoint_type="standings",
            url_pattern="ligas/{league_id}/clasificacion",
            parser_type="table_standings"
        )

    def test_endpoint_creation(self):
        self.assertEqual(self.endpoint.league, self.league)
        self.assertEqual(self.endpoint.endpoint_type, "standings")
        self.assertTrue(self.endpoint.is_active)

    def test_endpoint_str(self):
        expected = f"{self.league.name} - Clasificación"
        self.assertEqual(str(self.endpoint), expected)

    def test_get_full_url(self):
        url = self.endpoint.get_full_url()
        expected = f"{self.league.base_url}/ligas/{self.league.federation_id}/clasificacion"
        self.assertEqual(url, expected)


class CompetitionsViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        self.league = League.objects.create(
            name="Liga Test",
            federation_id="12345",
            season="2024-25",
            is_active=True
        )

    def test_league_list_view(self):
        response = self.client.get(reverse('competitions:league_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Liga Test")

    def test_league_detail_view(self):
        response = self.client.get(reverse('competitions:league_detail', args=[self.league.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Liga Test")

    def test_match_calendar_view(self):
        response = self.client.get(reverse('competitions:match_calendar'))
        self.assertEqual(response.status_code, 200)

    def test_standings_view(self):
        response = self.client.get(reverse('competitions:standings', args=[self.league.id]))
        self.assertEqual(response.status_code, 200)

    def test_league_list_with_filters(self):
        # Test competition type filter
        response = self.client.get(reverse('competitions:league_list'), {'competition_type': 'regular'})
        self.assertEqual(response.status_code, 200)
        
        # Test search
        response = self.client.get(reverse('competitions:league_list'), {'search': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Liga Test")

    def test_match_calendar_with_filters(self):
        # Test league filter
        response = self.client.get(reverse('competitions:match_calendar'), {'league': self.league.id})
        self.assertEqual(response.status_code, 200)
        
        # Test status filter
        response = self.client.get(reverse('competitions:match_calendar'), {'status': 'scheduled'})
        self.assertEqual(response.status_code, 200)