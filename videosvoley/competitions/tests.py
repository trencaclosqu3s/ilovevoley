"""
Tests para la app competitions.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import League, Match, Standing, ScrapingEndpoint
from videosvoley.content.models import Category
from videosvoley.teams.models import Team

User = get_user_model()


class CompetitionsModelsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.team = Team.objects.create(
            name='SANT JOSEP Senior',
            category=self.category,
            is_active=True
        )
        
        self.league = League.objects.create(
            name='Liga Test',
            category=self.category,
            season='2024-25',
            is_active=True
        )

    def test_league_creation(self):
        """Test creación de liga"""
        league = League.objects.create(
            name='Test League',
            description='Liga de prueba',
            season='2024-25',
            competition_type='official',
            category=self.category,
            is_active=True
        )
        
        self.assertEqual(league.name, 'Test League')
        self.assertEqual(league.season, '2024-25')
        self.assertEqual(league.competition_type, 'official')
        self.assertEqual(league.category, self.category)
        self.assertTrue(league.is_active)

    def test_match_creation(self):
        """Test creación de partido"""
        match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            venue='Polideportivo Test',
            status='scheduled'
        )
        
        self.assertEqual(match.league, self.league)
        self.assertEqual(match.home_team, self.team)
        self.assertEqual(match.away_team, self.team)
        self.assertEqual(match.status, 'scheduled')

    def test_match_with_text_teams(self):
        """Test creación de partido con equipos en texto"""
        match = Match.objects.create(
            league=self.league,
            home_team_text='Equipo Local',
            away_team_text='Equipo Visitante',
            match_date=timezone.now(),
            venue='Polideportivo Test',
            status='scheduled'
        )
        
        self.assertEqual(match.home_team_text, 'Equipo Local')
        self.assertEqual(match.away_team_text, 'Equipo Visitante')
        self.assertEqual(match.home_team_display, 'Equipo Local')
        self.assertEqual(match.away_team_display, 'Equipo Visitante')

    def test_match_result(self):
        """Test resultado de partido"""
        match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            home_score=3,
            away_score=1,
            status='finished'
        )
        
        self.assertTrue(match.is_finished)
        self.assertEqual(match.result_display, '3 - 1')

    def test_standing_creation(self):
        """Test creación de clasificación"""
        standing = Standing.objects.create(
            league=self.league,
            team=self.team,
            position=1,
            matches_played=10,
            matches_won=8,
            matches_drawn=1,
            matches_lost=1,
            points_for=25,
            points_against=15,
            points=25
        )
        
        self.assertEqual(standing.league, self.league)
        self.assertEqual(standing.team, self.team)
        self.assertEqual(standing.position, 1)
        self.assertEqual(standing.point_difference, 10)
        self.assertEqual(standing.win_percentage, 80.0)

    def test_scraping_endpoint_creation(self):
        """Test creación de endpoint de scraping"""
        endpoint = ScrapingEndpoint.objects.create(
            league=self.league,
            endpoint_type='standings',
            url_pattern='https://example.com/standings/{season}',
            parser_type='html',
            is_active=True
        )
        
        self.assertEqual(endpoint.league, self.league)
        self.assertEqual(endpoint.endpoint_type, 'standings')
        self.assertEqual(endpoint.parser_type, 'html')
        self.assertTrue(endpoint.is_active)


class CompetitionsViewsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.league = League.objects.create(
            name='Liga Test',
            category=self.category,
            season='2024-25',
            is_active=True
        )

    def test_league_list_view(self):
        """Test vista de lista de ligas"""
        response = self.client.get('/competitions/ligas/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/competitions/ligas/')
        self.assertEqual(response.status_code, 200)

    def test_league_detail_view(self):
        """Test vista de detalle de liga"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/competitions/ligas/{self.league.id}/')
        self.assertEqual(response.status_code, 200)

    def test_calendar_view(self):
        """Test vista de calendario"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/competitions/calendario/')
        self.assertEqual(response.status_code, 200)

    def test_standings_view(self):
        """Test vista de clasificaciones"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/competitions/clasificaciones/')
        self.assertEqual(response.status_code, 200)

    def test_friendly_match_create_view_permission(self):
        """Test permisos para crear partido amistoso"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/competitions/partidos/amistoso/')
        self.assertEqual(response.status_code, 403)  # No permission
        
        # Agregar usuario al grupo VideoManagers
        from django.contrib.auth.models import Group
        group = Group.objects.create(name='VideoManagers')
        self.user.groups.add(group)
        
        response = self.client.get('/competitions/partidos/amistoso/')
        self.assertEqual(response.status_code, 200)


class CompetitionsFormsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.league = League.objects.create(
            name='Liga Test',
            category=self.category,
            season='2024-25',
            is_active=True
        )

    def test_friendly_match_form(self):
        """Test formulario de partido amistoso"""
        from .forms import FriendlyMatchForm
        
        form_data = {
            'category': self.category.id,
            'home_team_text': 'Equipo Local',
            'away_team_text': 'Equipo Visitante',
            'match_date': '2024-12-31T18:00',
            'venue': 'Polideportivo Test',
        }
        
        form = FriendlyMatchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_match_result_form(self):
        """Test formulario de resultado de partido"""
        from .forms import MatchResultForm
        
        form_data = {
            'home_score': 3,
            'away_score': 1,
            'status': 'finished'
        }
        
        form = MatchResultForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_league_form(self):
        """Test formulario de liga"""
        from .forms import LeagueForm
        
        form_data = {
            'name': 'Test League',
            'description': 'Liga de prueba',
            'season': '2024-25',
            'competition_type': 'official',
            'category': self.category.id,
            'is_active': True
        }
        
        form = LeagueForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_standing_form(self):
        """Test formulario de clasificación"""
        from .forms import StandingForm
        
        form_data = {
            'team': self.team.id,
            'position': 1,
            'matches_played': 10,
            'matches_won': 8,
            'matches_drawn': 1,
            'matches_lost': 1,
            'points_for': 25,
            'points_against': 15,
            'points': 25
        }
        
        form = StandingForm(data=form_data)
        self.assertTrue(form.is_valid())


class CompetitionsUtilsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.team = Team.objects.create(
            name='SANT JOSEP Senior',
            category=self.category,
            is_active=True
        )
        
        self.league = League.objects.create(
            name='Liga Test',
            category=self.category,
            season='2024-25',
            is_active=True
        )

    def test_calculate_team_stats(self):
        """Test cálculo de estadísticas de equipo"""
        from .utils import calculate_team_stats
        
        # Crear partidos de prueba
        Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            home_score=3,
            away_score=1,
            status='finished'
        )
        
        Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            home_score=2,
            away_score=2,
            status='finished'
        )
        
        stats = calculate_team_stats(self.team, self.league)
        
        self.assertEqual(stats['matches_played'], 2)
        self.assertEqual(stats['matches_won'], 1)
        self.assertEqual(stats['matches_drawn'], 1)
        self.assertEqual(stats['matches_lost'], 0)
        self.assertEqual(stats['points_for'], 5)
        self.assertEqual(stats['points_against'], 3)
        self.assertEqual(stats['points'], 4)

    def test_get_team_matches(self):
        """Test obtención de partidos de equipo"""
        from .utils import get_team_matches
        
        # Crear partido de prueba
        match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            status='scheduled'
        )
        
        matches = get_team_matches(self.team)
        self.assertEqual(matches.count(), 1)
        self.assertEqual(matches.first(), match)

    def test_get_league_stats(self):
        """Test obtención de estadísticas de liga"""
        from .utils import get_league_stats
        
        # Crear partidos de prueba
        Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            home_score=3,
            away_score=1,
            status='finished'
        )
        
        Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.team,
            match_date=timezone.now(),
            status='scheduled'
        )
        
        stats = get_league_stats(self.league)
        
        self.assertEqual(stats['total_matches'], 2)
        self.assertEqual(stats['finished_matches'], 1)
        self.assertEqual(stats['scheduled_matches'], 1)
        self.assertEqual(stats['total_goals'], 4)
        self.assertEqual(stats['average_goals_per_match'], 4.0)