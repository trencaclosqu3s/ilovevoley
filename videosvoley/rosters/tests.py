from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Person, PlayerRole, StaffRole

User = get_user_model()


class PersonModelTest(TestCase):
    def setUp(self):
        self.person = Person.objects.create(
            first_name="Juan",
            last_name="Pérez",
            email="juan@example.com",
            phone="123456789",
            birth_date="1990-01-01"
        )

    def test_person_creation(self):
        self.assertEqual(self.person.first_name, "Juan")
        self.assertEqual(self.person.last_name, "Pérez")
        self.assertEqual(self.person.email, "juan@example.com")
        self.assertTrue(self.person.is_active)

    def test_person_str(self):
        self.assertEqual(str(self.person), "Juan Pérez")

    def test_full_name(self):
        self.assertEqual(self.person.full_name, "Juan Pérez")

    def test_age_calculation(self):
        # La edad se calcula dinámicamente, por lo que solo verificamos que no sea None
        self.assertIsNotNone(self.person.age)

    def test_age_display(self):
        age_display = self.person.age_display
        self.assertIn("años", age_display)

    def test_contact_info(self):
        contact = self.person.contact_info
        self.assertIn("juan@example.com", contact)
        self.assertIn("123456789", contact)

    def test_photo_preview(self):
        # Sin foto
        preview = self.person.photo_preview
        self.assertEqual(preview, "Sin foto")

    def test_get_player_roles(self):
        roles = self.person.get_player_roles()
        self.assertEqual(roles.count(), 0)

    def test_get_staff_roles(self):
        roles = self.person.get_staff_roles()
        self.assertEqual(roles.count(), 0)

    def test_get_all_active_teams(self):
        teams = self.person.get_all_active_teams()
        self.assertEqual(len(teams), 0)

    def test_get_roles_summary(self):
        summary = self.person.get_roles_summary()
        self.assertIn('player_roles', summary)
        self.assertIn('staff_roles', summary)
        self.assertIn('total_teams', summary)


class PlayerRoleModelTest(TestCase):
    def setUp(self):
        self.person = Person.objects.create(
            first_name="Juan",
            last_name="Pérez",
            email="juan@example.com"
        )
        
        # Crear equipo temporal
        from videosvoley.videos.models import Team
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_test"
        )
        
        self.player_role = PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            jersey_number=10,
            position="setter"
        )

    def test_player_role_creation(self):
        self.assertEqual(self.player_role.person, self.person)
        self.assertEqual(self.player_role.team, self.team)
        self.assertEqual(self.player_role.jersey_number, 10)
        self.assertEqual(self.player_role.position, "setter")
        self.assertTrue(self.player_role.is_active)

    def test_player_role_str(self):
        expected = f"{self.person.full_name} (#{self.player_role.jersey_number}) - {self.team.name}"
        self.assertEqual(str(self.player_role), expected)

    def test_display_position(self):
        self.assertEqual(self.player_role.display_position, "Colocador")

    def test_team_category(self):
        # Sin categoría asignada
        self.assertEqual(self.player_role.team_category, "Sin categoría")

    def test_clean_validation(self):
        # Crear otro rol con el mismo número de dorsal
        person2 = Person.objects.create(
            first_name="María",
            last_name="García",
            email="maria@example.com"
        )
        
        with self.assertRaises(ValidationError):
            PlayerRole.objects.create(
                person=person2,
                team=self.team,
                jersey_number=10,  # Mismo número
                position="outside_hitter"
            )


class StaffRoleModelTest(TestCase):
    def setUp(self):
        self.person = Person.objects.create(
            first_name="Ana",
            last_name="López",
            email="ana@example.com"
        )
        
        # Crear equipo temporal
        from videosvoley.videos.models import Team
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_test"
        )
        
        self.staff_role = StaffRole.objects.create(
            person=self.person,
            team=self.team,
            role="head_coach"
        )

    def test_staff_role_creation(self):
        self.assertEqual(self.staff_role.person, self.person)
        self.assertEqual(self.staff_role.team, self.team)
        self.assertEqual(self.staff_role.role, "head_coach")
        self.assertTrue(self.staff_role.is_active)

    def test_staff_role_str(self):
        expected = f"{self.person.full_name} - Entrenador/a ({self.team.name})"
        self.assertEqual(str(self.staff_role), expected)

    def test_display_role(self):
        self.assertEqual(self.staff_role.display_role, "Entrenador/a")

    def test_team_category(self):
        # Sin categoría asignada
        self.assertEqual(self.staff_role.team_category, "Sin categoría")


class RostersViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.person = Person.objects.create(
            first_name="Juan",
            last_name="Pérez",
            email="juan@example.com"
        )
        
        # Crear equipo temporal
        from videosvoley.videos.models import Team
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_test"
        )
        
        self.player_role = PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            jersey_number=10,
            position="setter"
        )

    def test_person_list_view(self):
        response = self.client.get(reverse('rosters:person_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Juan Pérez")

    def test_person_detail_view(self):
        response = self.client.get(reverse('rosters:person_detail', args=[self.person.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Juan Pérez")

    def test_team_roster_view(self):
        response = self.client.get(reverse('rosters:team_roster', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipo Test")

    def test_roster_by_position_view(self):
        response = self.client.get(reverse('rosters:roster_by_position', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipo Test")

    def test_person_list_with_filters(self):
        # Test search filter
        response = self.client.get(reverse('rosters:person_list'), {'search': 'Juan'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Juan Pérez")
        
        # Test role filter
        response = self.client.get(reverse('rosters:person_list'), {'role': 'players'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Juan Pérez")

    def test_search_persons_ajax(self):
        response = self.client.get(reverse('rosters:search_persons'), {'q': 'Juan'})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            'persons': [{
                'id': self.person.id,
                'name': 'Juan Pérez',
                'email': 'juan@example.com',
                'age': self.person.age,
                'is_active': True
            }]
        })

    def test_roster_export_view(self):
        response = self.client.get(reverse('rosters:roster_export', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('team', data)
        self.assertIn('players', data)
        self.assertIn('staff', data)

    def test_person_statistics_ajax(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('rosters:person_statistics', args=[self.person.id]))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('stats', data)

    def test_assign_jersey_number_ajax(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('rosters:assign_jersey_number', args=[self.player_role.id]),
            {'jersey_number': '15'}
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['jersey_number'], 15)


class RostersManagersTest(TestCase):
    def setUp(self):
        self.person1 = Person.objects.create(
            first_name="Juan",
            last_name="Pérez",
            email="juan@example.com",
            is_active=True
        )
        
        self.person2 = Person.objects.create(
            first_name="María",
            last_name="García",
            email="maria@example.com",
            is_active=False
        )
        
        # Crear equipo temporal
        from videosvoley.videos.models import Team
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_test"
        )
        
        self.player_role = PlayerRole.objects.create(
            person=self.person1,
            team=self.team,
            jersey_number=10,
            position="setter"
        )

    def test_person_manager_active(self):
        active_persons = Person.objects.active()
        self.assertEqual(active_persons.count(), 1)
        self.assertEqual(active_persons.first(), self.person1)

    def test_person_manager_with_roles(self):
        persons_with_roles = Person.objects.with_roles()
        self.assertEqual(persons_with_roles.count(), 1)
        self.assertEqual(persons_with_roles.first(), self.person1)

    def test_person_manager_players_only(self):
        players = Person.objects.players_only()
        self.assertEqual(players.count(), 1)
        self.assertEqual(players.first(), self.person1)

    def test_player_role_manager_active(self):
        active_roles = PlayerRole.objects.active()
        self.assertEqual(active_roles.count(), 1)
        self.assertEqual(active_roles.first(), self.player_role)

    def test_player_role_manager_by_team(self):
        team_roles = PlayerRole.objects.by_team(self.team)
        self.assertEqual(team_roles.count(), 1)
        self.assertEqual(team_roles.first(), self.player_role)

    def test_player_role_manager_by_position(self):
        setter_roles = PlayerRole.objects.by_position("setter")
        self.assertEqual(setter_roles.count(), 1)
        self.assertEqual(setter_roles.first(), self.player_role)

    def test_player_role_manager_with_jersey_numbers(self):
        roles_with_jersey = PlayerRole.objects.with_jersey_numbers()
        self.assertEqual(roles_with_jersey.count(), 1)
        self.assertEqual(roles_with_jersey.first(), self.player_role)


class RostersFormsTest(TestCase):
    def setUp(self):
        self.person = Person.objects.create(
            first_name="Juan",
            last_name="Pérez",
            email="juan@example.com"
        )
        
        # Crear equipo temporal
        from videosvoley.videos.models import Team
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_test"
        )

    def test_person_form_valid(self):
        form_data = {
            'first_name': 'María',
            'last_name': 'García',
            'email': 'maria@example.com',
            'is_active': True
        }
        form = PersonForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_person_form_invalid_age(self):
        form_data = {
            'first_name': 'María',
            'last_name': 'García',
            'birth_date': '2020-01-01',  # Muy joven
            'is_active': True
        }
        form = PersonForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_player_role_form_valid(self):
        form_data = {
            'person': self.person.id,
            'team': self.team.id,
            'jersey_number': 15,
            'position': 'outside_hitter',
            'is_active': True
        }
        form = PlayerRoleForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_player_role_form_duplicate_jersey(self):
        # Crear primer rol
        PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            jersey_number=15,
            position="setter"
        )
        
        # Intentar crear segundo rol con mismo número
        person2 = Person.objects.create(
            first_name="María",
            last_name="García",
            email="maria@example.com"
        )
        
        form_data = {
            'person': person2.id,
            'team': self.team.id,
            'jersey_number': 15,  # Mismo número
            'position': 'outside_hitter',
            'is_active': True
        }
        form = PlayerRoleForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_staff_role_form_valid(self):
        form_data = {
            'person': self.person.id,
            'team': self.team.id,
            'role': 'head_coach',
            'is_active': True
        }
        form = StaffRoleForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_person_filter_form_valid(self):
        form_data = {
            'search': 'Juan',
            'role': 'players',
            'age_min': 18,
            'age_max': 35,
            'active_only': True
        }
        form = PersonFilterForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_person_filter_form_invalid_age_range(self):
        form_data = {
            'age_min': 35,
            'age_max': 18,  # Mínimo mayor que máximo
        }
        form = PersonFilterForm(data=form_data)
        self.assertFalse(form.is_valid())