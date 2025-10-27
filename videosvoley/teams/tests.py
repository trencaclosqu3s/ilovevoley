"""
Tests para la app teams.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Team, Club
from videosvoley.content.models import Category

User = get_user_model()


class TeamsModelsTestCase(TestCase):
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
        
        self.club = Club.objects.create(
            official_name='Club de Prueba',
            short_name='CP',
            city='Ciudad Test',
            province='Provincia Test',
            is_active=True
        )
        
        self.team = Team.objects.create(
            name='Equipo Test',
            category=self.category,
            club=self.club,
            is_active=True
        )

    def test_team_creation(self):
        """Test creación de equipo"""
        team = Team.objects.create(
            name='Test Team',
            category=self.category,
            club=self.club,
            is_active=True
        )
        
        self.assertEqual(team.name, 'Test Team')
        self.assertEqual(team.category, self.category)
        self.assertEqual(team.club, self.club)
        self.assertTrue(team.is_active)

    def test_club_creation(self):
        """Test creación de club"""
        club = Club.objects.create(
            official_name='Test Club',
            short_name='TC',
            city='Test City',
            province='Test Province',
            is_active=True
        )
        
        self.assertEqual(club.official_name, 'Test Club')
        self.assertEqual(club.short_name, 'TC')
        self.assertEqual(club.city, 'Test City')
        self.assertEqual(club.province, 'Test Province')
        self.assertTrue(club.is_active)

    def test_team_str_representation(self):
        """Test representación string del equipo"""
        self.assertEqual(str(self.team), 'Equipo Test')

    def test_club_str_representation(self):
        """Test representación string del club"""
        self.assertEqual(str(self.club), 'Club de Prueba')

    def test_team_without_club(self):
        """Test equipo sin club"""
        team = Team.objects.create(
            name='Team Without Club',
            category=self.category,
            is_active=True
        )
        
        self.assertIsNone(team.club)
        self.assertEqual(team.name, 'Team Without Club')

    def test_club_without_short_name(self):
        """Test club sin nombre corto"""
        club = Club.objects.create(
            official_name='Club Without Short Name',
            city='Test City',
            province='Test Province',
            is_active=True
        )
        
        self.assertIsNone(club.short_name)
        self.assertEqual(club.official_name, 'Club Without Short Name')


class TeamsViewsTestCase(TestCase):
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
        
        self.club = Club.objects.create(
            official_name='Club de Prueba',
            short_name='CP',
            city='Ciudad Test',
            province='Provincia Test',
            is_active=True
        )
        
        self.team = Team.objects.create(
            name='Equipo Test',
            category=self.category,
            club=self.club,
            is_active=True
        )

    def test_team_list_view(self):
        """Test vista de lista de equipos"""
        response = self.client.get('/teams/equipos/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/teams/equipos/')
        self.assertEqual(response.status_code, 200)

    def test_team_detail_view(self):
        """Test vista de detalle de equipo"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/teams/equipos/{self.team.id}/')
        self.assertEqual(response.status_code, 200)

    def test_team_roster_view(self):
        """Test vista de plantilla de equipo"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/teams/equipos/{self.team.id}/plantilla/')
        self.assertEqual(response.status_code, 200)

    def test_club_list_view(self):
        """Test vista de lista de clubs"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/teams/clubs/')
        self.assertEqual(response.status_code, 200)

    def test_club_detail_view(self):
        """Test vista de detalle de club"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/teams/clubs/{self.club.id}/')
        self.assertEqual(response.status_code, 200)

    def test_roster_overview_view(self):
        """Test vista de resumen de plantillas"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/teams/plantillas/')
        self.assertEqual(response.status_code, 200)

    def test_ajax_search_teams(self):
        """Test API de búsqueda de equipos"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/teams/api/equipos/buscar/?q=Test')
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'teams': []})

    def test_ajax_search_clubs(self):
        """Test API de búsqueda de clubs"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/teams/api/clubs/buscar/?q=Club')
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'clubs': []})


class TeamsFormsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.club = Club.objects.create(
            official_name='Club de Prueba',
            short_name='CP',
            city='Ciudad Test',
            province='Provincia Test',
            is_active=True
        )

    def test_team_form(self):
        """Test formulario de equipo"""
        from .forms import TeamForm
        
        form_data = {
            'name': 'Test Team',
            'category': self.category.id,
            'club': self.club.id,
            'is_active': True
        }
        
        form = TeamForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_club_form(self):
        """Test formulario de club"""
        from .forms import ClubForm
        
        form_data = {
            'official_name': 'Test Club',
            'short_name': 'TC',
            'city': 'Test City',
            'province': 'Test Province',
            'is_active': True
        }
        
        form = ClubForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_team_search_form(self):
        """Test formulario de búsqueda de equipos"""
        from .forms import TeamSearchForm
        
        form_data = {
            'search': 'Test',
            'category': self.category.id
        }
        
        form = TeamSearchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_club_search_form(self):
        """Test formulario de búsqueda de clubs"""
        from .forms import ClubSearchForm
        
        form_data = {
            'search': 'Club'
        }
        
        form = ClubSearchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_team_form_validation(self):
        """Test validación del formulario de equipo"""
        from .forms import TeamForm
        
        # Crear equipo existente
        Team.objects.create(
            name='Existing Team',
            category=self.category,
            is_active=True
        )
        
        # Intentar crear otro equipo con el mismo nombre en la misma categoría
        form_data = {
            'name': 'Existing Team',
            'category': self.category.id,
            'is_active': True
        }
        
        form = TeamForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('Ya existe un equipo llamado', str(form.errors))

    def test_club_form_validation(self):
        """Test validación del formulario de club"""
        from .forms import ClubForm
        
        # Crear club existente
        Club.objects.create(
            official_name='Existing Club',
            city='Test City',
            province='Test Province',
            is_active=True
        )
        
        # Intentar crear otro club con el mismo nombre oficial
        form_data = {
            'official_name': 'Existing Club',
            'city': 'Test City',
            'province': 'Test Province',
            'is_active': True
        }
        
        form = ClubForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('Ya existe un club con el nombre oficial', str(form.errors))


class TeamsUtilsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.category = Category.objects.create(
            name='Senior',
            description='Categoría Senior',
            is_active=True
        )
        
        self.club = Club.objects.create(
            official_name='Club de Prueba',
            short_name='CP',
            city='Ciudad Test',
            province='Provincia Test',
            is_active=True
        )
        
        self.team = Team.objects.create(
            name='Equipo Test',
            category=self.category,
            club=self.club,
            is_active=True
        )

    def test_get_team_stats(self):
        """Test obtención de estadísticas de equipo"""
        from .utils import get_team_stats
        
        stats = get_team_stats(self.team)
        
        self.assertIn('total_matches', stats)
        self.assertIn('won_matches', stats)
        self.assertIn('drawn_matches', stats)
        self.assertIn('lost_matches', stats)
        self.assertIn('win_percentage', stats)
        self.assertIn('total_players', stats)
        self.assertIn('total_staff', stats)

    def test_get_club_stats(self):
        """Test obtención de estadísticas de club"""
        from .utils import get_club_stats
        
        stats = get_club_stats(self.club)
        
        self.assertIn('total_teams', stats)
        self.assertIn('total_players', stats)
        self.assertIn('total_staff', stats)
        self.assertIn('total_matches', stats)
        self.assertIn('won_matches', stats)
        self.assertIn('win_percentage', stats)

    def test_get_teams_by_category(self):
        """Test obtención de equipos por categoría"""
        from .utils import get_teams_by_category
        
        teams = get_teams_by_category(self.category)
        self.assertEqual(teams.count(), 1)
        self.assertEqual(teams.first(), self.team)

    def test_get_teams_by_club(self):
        """Test obtención de equipos por club"""
        from .utils import get_teams_by_club
        
        teams = get_teams_by_club(self.club)
        self.assertEqual(teams.count(), 1)
        self.assertEqual(teams.first(), self.team)

    def test_search_teams(self):
        """Test búsqueda de equipos"""
        from .utils import search_teams
        
        teams = search_teams('Test')
        self.assertEqual(teams.count(), 1)
        self.assertEqual(teams.first(), self.team)

    def test_search_clubs(self):
        """Test búsqueda de clubs"""
        from .utils import search_clubs
        
        clubs = search_clubs('Club')
        self.assertEqual(clubs.count(), 1)
        self.assertEqual(clubs.first(), self.club)

    def test_get_team_roster(self):
        """Test obtención de plantilla de equipo"""
        from .utils import get_team_roster
        
        roster = get_team_roster(self.team)
        
        self.assertIn('players_by_position', roster)
        self.assertIn('staff_by_role', roster)
        self.assertIn('total_players', roster)
        self.assertIn('total_staff', roster)

    def test_get_club_teams_by_category(self):
        """Test obtención de equipos de club por categoría"""
        from .utils import get_club_teams_by_category
        
        teams_by_category = get_club_teams_by_category(self.club)
        
        self.assertIn('Senior', teams_by_category)
        self.assertEqual(len(teams_by_category['Senior']), 1)
        self.assertEqual(teams_by_category['Senior'][0], self.team)