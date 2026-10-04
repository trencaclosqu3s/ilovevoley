from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import resolve, reverse

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos.views import teams as videos_views_teams


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class TeamsReExportCompatibilityTest(TestCase):
    """Las vistas importadas históricamente desde ``videos`` sirven las URLs canónicas."""

    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club',
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category,
            federation_id='REEXPORT-T1', is_active=True,
        )

    def test_legacy_views_resolve_to_the_canonical_team_urls(self):
        routes = [
            ('team_list', 'teams:team_list', []),
            ('team_roster', 'teams:team_roster', [self.team.id]),
            ('ajax_register_team', 'teams:ajax_register_team', []),
        ]
        for attr, route, args in routes:
            with self.subTest(view=attr):
                legacy_view = getattr(videos_views_teams, attr)
                self.assertIs(resolve(reverse(route, args=args)).func, legacy_view)

    def test_legacy_team_list_renders_the_tenant_teams(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('teams:team_list'), HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.resolver_match.func, videos_views_teams.team_list)
        self.assertIn(self.team, response.context['teams'])


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
        self.org.club = self.club
        self.org.save(update_fields=['club'])
        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org, is_approved=True, role='manager'
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

    def test_team_roster_devuelve_404_para_equipo_ajeno(self):
        self.client.force_login(self.user)
        url = reverse('teams:team_roster', args=[self.other_team.id])
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_teams_ajax_register_team_url_resolves_and_creates_team(self):
        self.client.force_login(self.manager)
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

    def test_basic_member_cannot_register_team_returns_403(self):
        self.client.force_login(self.user)
        url = reverse('teams:ajax_register_team')
        response = self.client.post(
            url,
            {'name': 'Team Member', 'category_id': self.category.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)

    def test_register_team_validates_name_syntax_and_length(self):
        self.client.force_login(self.manager)
        url = reverse('teams:ajax_register_team')
        invalid_names = [
            'A',  # Demasiado corto (<2)
            'A' * 101,  # Demasiado largo (>100)
            'Team\nNewline',  # Carácter de control \n
            'Team\x00Null',  # Carácter de control \x00
            'Team\tTab',  # Carácter de control \t
        ]
        for name in invalid_names:
            response = self.client.post(
                url,
                {'name': name, 'category_id': self.category.id},
                HTTP_HOST='testclub.ilovevoley.es',
            )
            self.assertEqual(response.status_code, 400, f"Expected 400 for invalid name: {name!r}")

    def test_register_team_forces_tenant_club_ignoring_payload(self):
        other_club = Club.objects.create(official_name='Other Club', federation_id='OTHER-CLUB')
        self.client.force_login(self.manager)
        url = reverse('teams:ajax_register_team')
        response = self.client.post(
            url,
            {
                'name': 'Tenant Team Protected',
                'category_id': self.category.id,
                'club_id': other_club.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        team = Team.objects.get(name='Tenant Team Protected')
        self.assertEqual(team.club, self.club)

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
        actual = Person.objects.create(first_name='Actual', last_name='Uno')
        actual.organizations.add(self.org)
        pasado = Person.objects.create(first_name='Pasado', last_name='Dos')
        pasado.organizations.add(self.org)
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


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class TeamRosterStatsConsistencyTests(TestCase):
    """Las estadísticas de cabecera reflejan la plantilla completa; los filtros
    de posición/rol solo acotan las listas mostradas."""

    def setUp(self):
        from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club',
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category,
            federation_id='T-STATS', is_active=True,
        )
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )
        setter = Person.objects.create(first_name='Ana', last_name='Coloca')
        setter.organizations.add(self.org)
        libero = Person.objects.create(first_name='Bea', last_name='Libera')
        libero.organizations.add(self.org)
        coach = Person.objects.create(first_name='Carla', last_name='Entrena')
        coach.organizations.add(self.org)
        PlayerRole.objects.create(
            person=setter, team=self.team, season=self.season,
            position='setter', jersey_number=1,
        )
        PlayerRole.objects.create(
            person=libero, team=self.team, season=self.season,
            position='libero', jersey_number=2,
        )
        StaffRole.objects.create(
            person=coach, team=self.team, season=self.season, role='head_coach',
        )

    def _get(self, query=''):
        self.client.force_login(self.user)
        return self.client.get(
            reverse('teams:team_roster', args=[self.team.id]) + query,
            HTTP_HOST='testclub.ilovevoley.es',
        )

    def test_stats_no_menguan_al_filtrar_por_posicion(self):
        full = self._get()
        filtered = self._get('?position=setter')
        self.assertEqual(filtered.context['stats']['total_players'], 2)
        self.assertEqual(
            filtered.context['stats']['total_players'],
            full.context['stats']['total_players'],
        )
        self.assertEqual(filtered.context['stats']['positions_covered'], 2)
        self.assertEqual(len(filtered.context['player_roles']), 1)

    def test_stats_no_menguan_al_filtrar_por_rol_de_staff(self):
        full = self._get()
        filtered = self._get('?role=delegate')
        self.assertEqual(filtered.context['stats']['total_staff'], 1)
        self.assertEqual(
            filtered.context['stats']['total_staff'],
            full.context['stats']['total_staff'],
        )
        self.assertEqual(len(filtered.context['staff_roles']), 0)
        self.assertEqual(len(filtered.context['player_roles']), 2)

