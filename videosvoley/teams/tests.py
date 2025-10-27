from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from .models import Club, Team

User = get_user_model()


class ClubModelTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(
            federation_id="12345",
            official_name="Club Test",
            president="Juan Pérez",
            email="test@club.com",
            province="Baleares"
        )

    def test_club_creation(self):
        self.assertEqual(self.club.official_name, "Club Test")
        self.assertEqual(self.club.federation_id, "12345")
        self.assertEqual(self.club.president, "Juan Pérez")

    def test_club_str(self):
        self.assertEqual(str(self.club), "Club Test")

    def test_logo_federation_url(self):
        expected_url = f'https://voleibolib.federatio.com/fichas/clubes/{self.club.federation_id}.jpg'
        self.assertEqual(self.club.logo_federation_url, expected_url)

    def test_display_logo(self):
        # Sin logo propio, debería usar el de la federación
        self.assertEqual(self.club.display_logo, self.club.logo_federation_url)
        
        # Con logo propio
        self.club.logo_url = "https://example.com/logo.jpg"
        self.assertEqual(self.club.display_logo, "https://example.com/logo.jpg")

    def test_active_teams_count(self):
        # Sin equipos
        self.assertEqual(self.club.active_teams_count, 0)
        
        # Con equipos activos e inactivos
        Team.objects.create(
            name="Equipo A",
            federation_id="team_a",
            club=self.club,
            is_active=True
        )
        Team.objects.create(
            name="Equipo B",
            federation_id="team_b",
            club=self.club,
            is_active=False
        )
        self.assertEqual(self.club.active_teams_count, 1)

    def test_total_teams_count(self):
        # Sin equipos
        self.assertEqual(self.club.total_teams_count, 0)
        
        # Con equipos
        Team.objects.create(
            name="Equipo A",
            federation_id="team_a",
            club=self.club
        )
        Team.objects.create(
            name="Equipo B",
            federation_id="team_b",
            club=self.club
        )
        self.assertEqual(self.club.total_teams_count, 2)


class TeamModelTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(
            federation_id="12345",
            official_name="Club Test",
            province="Baleares"
        )
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_123",
            club=self.club,
            is_active=True
        )

    def test_team_creation(self):
        self.assertEqual(self.team.name, "Equipo Test")
        self.assertEqual(self.team.federation_id, "team_123")
        self.assertEqual(self.team.club, self.club)
        self.assertTrue(self.team.is_active)

    def test_team_str(self):
        self.assertEqual(str(self.team), "Equipo Test")

    def test_display_logo(self):
        # Sin logo propio, debería usar el del club
        self.assertEqual(self.team.display_logo, self.club.logo_federation_url)
        
        # Con logo propio
        self.team.logo_url = "https://example.com/team_logo.jpg"
        self.assertEqual(self.team.display_logo, "https://example.com/team_logo.jpg")

    def test_full_name(self):
        # Sin patrocinador
        self.assertEqual(self.team.full_name, "Equipo Test")
        
        # Con patrocinador
        self.team.sponsor_name = "Patrocinador"
        self.assertEqual(self.team.full_name, "Equipo Test - Patrocinador")

    def test_is_our_team(self):
        # Este test requeriría configuración en settings
        # Por ahora solo verificar que no falle
        self.assertIsInstance(self.team.is_our_team, bool)

    def test_get_statistics(self):
        stats = self.team.get_statistics()
        
        self.assertIn('total_matches', stats)
        self.assertIn('finished_matches', stats)
        self.assertIn('scheduled_matches', stats)
        self.assertIn('wins', stats)
        self.assertIn('losses', stats)
        self.assertIn('win_percentage', stats)


class TeamsViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            is_approved=True
        )
        
        self.club = Club.objects.create(
            federation_id="12345",
            official_name="Club Test",
            province="Baleares"
        )
        
        self.team = Team.objects.create(
            name="Equipo Test",
            federation_id="team_123",
            club=self.club,
            is_active=True
        )

    def test_club_list_view(self):
        response = self.client.get(reverse('teams:club_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Club Test")

    def test_club_detail_view(self):
        response = self.client.get(reverse('teams:club_detail', args=[self.club.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Club Test")

    def test_team_list_view(self):
        response = self.client.get(reverse('teams:team_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipo Test")

    def test_team_detail_view(self):
        response = self.client.get(reverse('teams:team_detail', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipo Test")

    def test_team_roster_view(self):
        response = self.client.get(reverse('teams:team_roster', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Funcionalidad de plantilla en desarrollo")

    def test_club_list_with_filters(self):
        # Test province filter
        response = self.client.get(reverse('teams:club_list'), {'province': 'Baleares'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Club Test")
        
        # Test search
        response = self.client.get(reverse('teams:club_list'), {'search': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Club Test")

    def test_team_list_with_filters(self):
        # Test club filter
        response = self.client.get(reverse('teams:team_list'), {'club': self.club.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipo Test")
        
        # Test active only filter
        response = self.client.get(reverse('teams:team_list'), {'active_only': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Equipo Test")

    def test_search_teams_ajax(self):
        response = self.client.get(reverse('teams:search_teams'), {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            'teams': [{
                'id': self.team.id,
                'name': 'Equipo Test',
                'club': 'Club Test',
                'category': '',
                'is_active': True
            }]
        })

    def test_search_clubs_ajax(self):
        response = self.client.get(reverse('teams:search_clubs'), {'q': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            'clubs': [{
                'id': self.club.id,
                'name': 'Club Test',
                'federation_id': '12345',
                'province': 'Baleares',
                'teams_count': 1
            }]
        })

    def test_team_statistics_ajax(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('teams:team_statistics', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('stats', data)


class TeamsManagersTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(
            federation_id="12345",
            official_name="Club Test",
            province="Baleares"
        )
        
        self.active_team = Team.objects.create(
            name="Equipo Activo",
            federation_id="team_active",
            club=self.club,
            is_active=True
        )
        
        self.inactive_team = Team.objects.create(
            name="Equipo Inactivo",
            federation_id="team_inactive",
            club=self.club,
            is_active=False
        )

    def test_team_manager_active(self):
        active_teams = Team.objects.active()
        self.assertEqual(active_teams.count(), 1)
        self.assertEqual(active_teams.first(), self.active_team)

    def test_team_manager_by_club(self):
        club_teams = Team.objects.by_club(self.club)
        self.assertEqual(club_teams.count(), 1)
        self.assertEqual(club_teams.first(), self.active_team)

    def test_club_manager_with_teams(self):
        clubs_with_teams = Club.objects.with_teams()
        self.assertEqual(clubs_with_teams.count(), 1)
        self.assertEqual(clubs_with_teams.first(), self.club)

    def test_club_manager_with_active_teams(self):
        clubs_with_active_teams = Club.objects.with_active_teams()
        self.assertEqual(clubs_with_active_teams.count(), 1)
        self.assertEqual(clubs_with_active_teams.first(), self.club)

    def test_club_manager_by_province(self):
        clubs_by_province = Club.objects.by_province("Baleares")
        self.assertEqual(clubs_by_province.count(), 1)
        self.assertEqual(clubs_by_province.first(), self.club)