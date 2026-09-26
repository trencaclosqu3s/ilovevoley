from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams import views as teams_views
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos.views import teams as videos_views_teams


class TeamsReExportCompatibilityTest(TestCase):
    """Verifica que las importaciones históricas desde videos sigan funcionando."""

    def test_views_are_reexported(self):
        self.assertIs(videos_views_teams.ajax_register_team, teams_views.ajax_register_team)
        self.assertIs(videos_views_teams.team_list, teams_views.team_list)
        self.assertIs(videos_views_teams.team_roster, teams_views.team_roster)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class TeamViewUrlTests(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            club_team_names={'1': 'Test Club'},
            is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True
        )
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(
            official_name='Club Voleibol Test',
            federation_id='CLUB-TEST',
        )
        self.team = Team.objects.create(
            name='Test Club Senior',
            category=self.category,
            club=self.club,
            federation_id='TEAM-TEST-1',
            is_active=True,
        )
        self.other_team = Team.objects.create(
            name='Rival Team',
            category=self.category,
            federation_id='TEAM-TEST-2',
            is_active=True,
        )

    def test_teams_team_list_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('teams:team_list')
        self.assertEqual(url, '/teams/equipos/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'teams/team_list.html')

    def test_backwards_compatible_videos_team_list_url_renders(self):
        self.client.force_login(self.user)
        url = reverse('videos:team_list')
        self.assertEqual(url, '/videos/equipos/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'teams/team_list.html')

    def test_teams_team_roster_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('teams:team_roster', args=[self.team.id])
        self.assertEqual(url, f'/teams/equipos/{self.team.id}/plantilla/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'teams/team_roster.html')

    def test_backwards_compatible_videos_team_roster_url_renders(self):
        self.client.force_login(self.user)
        url = reverse('videos:team_roster', args=[self.team.id])
        self.assertEqual(url, f'/videos/equipos/{self.team.id}/plantilla/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'teams/team_roster.html')

    def test_team_roster_devuelve_404_para_equipo_ajeno(self):
        self.client.force_login(self.user)
        url = reverse('teams:team_roster', args=[self.other_team.id])
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_teams_ajax_register_team_url_resolves_and_creates_team(self):
        self.client.force_login(self.user)
        url = reverse('teams:ajax_register_team')
        self.assertEqual(url, '/teams/ajax/register-team/')

        response = self.client.post(
            url,
            {
                'name': 'New Registered Team',
                'category_id': self.category.id,
                'club_id': self.club.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(Team.objects.filter(name='New Registered Team').exists())

    def test_backwards_compatible_videos_ajax_register_team_url(self):
        url = reverse('videos:ajax_register_team')
        self.assertEqual(url, '/videos/ajax/register-team/')

    def test_anonymous_cannot_register_team(self):
        url = reverse('teams:ajax_register_team')
        response = self.client.post(
            url,
            {
                'name': 'Hacker Team',
                'category_id': self.category.id,
                'club_id': self.club.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertFalse(Team.objects.filter(name='Hacker Team').exists())


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class TeamRosterSeasonFilterTests(TestCase):
    """La plantilla del equipo se filtra por temporada activa por defecto."""

    def setUp(self):
        from ilovevoley.rosters.models import Person, PlayerRole
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club',
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.category = Category.objects.create(name='Infantil', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Infantil', category=self.category,
            federation_id='T-INF', is_active=True,
        )
        self.current = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        self.past = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)
        actual = Person.objects.create(first_name='Actual', last_name='Uno', organization=self.org)
        pasado = Person.objects.create(first_name='Pasado', last_name='Dos', organization=self.org)
        PlayerRole.objects.create(person=actual, team=self.team, season=self.current, jersey_number=1)
        PlayerRole.objects.create(person=pasado, team=self.team, season=self.past, jersey_number=2)

    def _names(self, response):
        return {role.person.full_name for role in response.context['player_roles']}

    def test_default_muestra_temporada_activa(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('teams:team_roster', args=[self.team.id]), HTTP_HOST='testclub.ilovevoley.es'
        )
        self.assertEqual(self._names(response), {'Actual Uno'})

    def test_filtra_temporada_pasada(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('teams:team_roster', args=[self.team.id]) + f'?season={self.past.id}',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(self._names(response), {'Pasado Dos'})

    def test_todas_las_temporadas(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('teams:team_roster', args=[self.team.id]) + '?season=',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(self._names(response), {'Actual Uno', 'Pasado Dos'})

