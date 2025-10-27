"""
Tests para la app rosters.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Person, PlayerRole, StaffRole
from videosvoley.teams.models import Team, Club
from videosvoley.content.models import Category

User = get_user_model()


class RostersModelsTestCase(TestCase):
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
        
        self.person = Person.objects.create(
            first_name='Juan',
            last_name='Pérez',
            email='juan@example.com',
            phone='123456789'
        )

    def test_person_creation(self):
        """Test creación de persona"""
        person = Person.objects.create(
            first_name='María',
            last_name='García',
            email='maria@example.com',
            phone='987654321'
        )
        
        self.assertEqual(person.first_name, 'María')
        self.assertEqual(person.last_name, 'García')
        self.assertEqual(person.email, 'maria@example.com')
        self.assertEqual(person.phone, '987654321')

    def test_person_str_representation(self):
        """Test representación string de la persona"""
        self.assertEqual(str(self.person), 'Juan Pérez')

    def test_person_get_full_name(self):
        """Test método get_full_name"""
        self.assertEqual(self.person.get_full_name(), 'Juan Pérez')

    def test_player_role_creation(self):
        """Test creación de rol de jugador"""
        role = PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            position='Colocador',
            jersey_number=10,
            is_active=True
        )
        
        self.assertEqual(role.person, self.person)
        self.assertEqual(role.team, self.team)
        self.assertEqual(role.position, 'Colocador')
        self.assertEqual(role.jersey_number, 10)
        self.assertTrue(role.is_active)

    def test_staff_role_creation(self):
        """Test creación de rol de staff"""
        role = StaffRole.objects.create(
            person=self.person,
            team=self.team,
            role='Entrenador',
            is_active=True
        )
        
        self.assertEqual(role.person, self.person)
        self.assertEqual(role.team, self.team)
        self.assertEqual(role.role, 'Entrenador')
        self.assertTrue(role.is_active)

    def test_player_role_str_representation(self):
        """Test representación string del rol de jugador"""
        role = PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            position='Colocador',
            jersey_number=10
        )
        
        expected = f"{self.person.get_full_name()} - {self.team.name} (Colocador)"
        self.assertEqual(str(role), expected)

    def test_staff_role_str_representation(self):
        """Test representación string del rol de staff"""
        role = StaffRole.objects.create(
            person=self.person,
            team=self.team,
            role='Entrenador'
        )
        
        expected = f"{self.person.get_full_name()} - {self.team.name} (Entrenador)"
        self.assertEqual(str(role), expected)


class RostersViewsTestCase(TestCase):
    def setUp(self):
        """Configurar datos de prueba"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.staff_user = User.objects.create_user(
            username='staffuser',
            email='staff@example.com',
            password='testpass123',
            is_approved=True,
            is_staff=True
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
        
        self.person = Person.objects.create(
            first_name='Juan',
            last_name='Pérez',
            email='juan@example.com',
            phone='123456789'
        )

    def test_person_list_view(self):
        """Test vista de lista de personas"""
        response = self.client.get('/rosters/personas/')
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/rosters/personas/')
        self.assertEqual(response.status_code, 200)

    def test_person_detail_view(self):
        """Test vista de detalle de persona"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/rosters/personas/{self.person.id}/')
        self.assertEqual(response.status_code, 200)

    def test_person_create_view_permission(self):
        """Test permisos para crear persona"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/rosters/personas/crear/')
        self.assertEqual(response.status_code, 403)  # No permission
        
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get('/rosters/personas/crear/')
        self.assertEqual(response.status_code, 200)

    def test_person_edit_view_permission(self):
        """Test permisos para editar persona"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/rosters/personas/{self.person.id}/editar/')
        self.assertEqual(response.status_code, 403)  # No permission
        
        self.client.login(username='staffuser', password='testpass123')
        response = self.client.get(f'/rosters/personas/{self.person.id}/editar/')
        self.assertEqual(response.status_code, 200)

    def test_roster_overview_view(self):
        """Test vista de resumen de plantillas"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/rosters/plantillas/')
        self.assertEqual(response.status_code, 200)

    def test_ajax_search_persons(self):
        """Test API de búsqueda de personas"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/rosters/api/personas/buscar/?q=Juan')
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'persons': []})

    def test_ajax_persons_by_team(self):
        """Test API de personas por equipo"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(f'/rosters/api/personas/por-equipo/?team_id={self.team.id}')
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'persons': []})


class RostersFormsTestCase(TestCase):
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
        
        self.person = Person.objects.create(
            first_name='Juan',
            last_name='Pérez',
            email='juan@example.com',
            phone='123456789'
        )

    def test_person_form(self):
        """Test formulario de persona"""
        from .forms import PersonForm
        
        form_data = {
            'first_name': 'María',
            'last_name': 'García',
            'email': 'maria@example.com',
            'phone': '987654321'
        }
        
        form = PersonForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_player_role_form(self):
        """Test formulario de rol de jugador"""
        from .forms import PlayerRoleForm
        
        form_data = {
            'team': self.team.id,
            'position': 'Colocador',
            'jersey_number': 10,
            'is_active': True
        }
        
        form = PlayerRoleForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_staff_role_form(self):
        """Test formulario de rol de staff"""
        from .forms import StaffRoleForm
        
        form_data = {
            'team': self.team.id,
            'role': 'Entrenador',
            'is_active': True
        }
        
        form = StaffRoleForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_person_search_form(self):
        """Test formulario de búsqueda de personas"""
        from .forms import PersonSearchForm
        
        form_data = {
            'search': 'Juan',
            'role': 'player'
        }
        
        form = PersonSearchForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_person_form_validation(self):
        """Test validación del formulario de persona"""
        from .forms import PersonForm
        
        # Crear persona existente
        Person.objects.create(
            first_name='Juan',
            last_name='Pérez',
            email='juan@example.com'
        )
        
        # Intentar crear otra persona con el mismo nombre y apellido
        form_data = {
            'first_name': 'Juan',
            'last_name': 'Pérez',
            'email': 'juan2@example.com'
        }
        
        form = PersonForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('Ya existe una persona llamada', str(form.errors))

    def test_player_role_form_validation(self):
        """Test validación del formulario de rol de jugador"""
        from .forms import PlayerRoleForm
        
        # Crear rol existente
        PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            jersey_number=10
        )
        
        # Intentar crear otro rol con el mismo número en el mismo equipo
        form_data = {
            'team': self.team.id,
            'jersey_number': 10,
            'is_active': True
        }
        
        form = PlayerRoleForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('Ya existe un jugador con el número', str(form.errors))


class RostersUtilsTestCase(TestCase):
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
        
        self.person = Person.objects.create(
            first_name='Juan',
            last_name='Pérez',
            email='juan@example.com',
            phone='123456789'
        )
        
        self.player_role = PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            position='Colocador',
            jersey_number=10,
            is_active=True
        )
        
        self.staff_role = StaffRole.objects.create(
            person=self.person,
            team=self.team,
            role='Entrenador',
            is_active=True
        )

    def test_get_person_stats(self):
        """Test obtención de estadísticas de persona"""
        from .utils import get_person_stats
        
        stats = get_person_stats(self.person)
        
        self.assertIn('total_teams', stats)
        self.assertIn('total_categories', stats)
        self.assertIn('player_roles', stats)
        self.assertIn('staff_roles', stats)
        self.assertIn('active_roles', stats)
        self.assertIn('teams', stats)
        self.assertIn('categories', stats)

    def test_get_team_roster_stats(self):
        """Test obtención de estadísticas de plantilla de equipo"""
        from .utils import get_team_roster_stats
        
        stats = get_team_roster_stats(self.team)
        
        self.assertIn('total_players', stats)
        self.assertIn('total_staff', stats)
        self.assertIn('total_members', stats)
        self.assertIn('positions_count', stats)
        self.assertIn('roles_count', stats)

    def test_get_persons_by_team(self):
        """Test obtención de personas por equipo"""
        from .utils import get_persons_by_team
        
        persons = get_persons_by_team(self.team)
        self.assertEqual(persons.count(), 1)
        self.assertEqual(persons.first(), self.person)

    def test_search_persons(self):
        """Test búsqueda de personas"""
        from .utils import search_persons
        
        persons = search_persons('Juan')
        self.assertEqual(persons.count(), 1)
        self.assertEqual(persons.first(), self.person)

    def test_get_person_teams(self):
        """Test obtención de equipos de una persona"""
        from .utils import get_person_teams
        
        teams = get_person_teams(self.person)
        
        self.assertIn('player_teams', teams)
        self.assertIn('staff_teams', teams)
        self.assertIn('all_teams', teams)

    def test_get_team_roster_by_position(self):
        """Test obtención de plantilla por posición"""
        from .utils import get_team_roster_by_position
        
        roster = get_team_roster_by_position(self.team)
        
        self.assertIn('players_by_position', roster)
        self.assertIn('staff_by_role', roster)
        self.assertIn('total_players', roster)
        self.assertIn('total_staff', roster)

    def test_get_roster_statistics(self):
        """Test obtención de estadísticas generales"""
        from .utils import get_roster_statistics
        
        stats = get_roster_statistics()
        
        self.assertIn('total_persons', stats)
        self.assertIn('active_player_roles', stats)
        self.assertIn('active_staff_roles', stats)
        self.assertIn('total_active_roles', stats)
        self.assertIn('teams_with_roster', stats)
        self.assertIn('persons_with_multiple_roles', stats)