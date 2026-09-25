from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters import forms as rosters_forms
from ilovevoley.rosters import views as rosters_views
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos.forms import rosters as vid_forms_rosters
from ilovevoley.videos.views import rosters as vid_views_rosters


class RostersReExportCompatibilityTest(TestCase):
    """Verifica que las importaciones históricas desde videos sigan funcionando."""

    def test_forms_are_reexported(self):
        self.assertIs(vid_forms_rosters.PersonForm, rosters_forms.PersonForm)
        self.assertIs(vid_forms_rosters.PlayerRoleForm, rosters_forms.PlayerRoleForm)
        self.assertIs(vid_forms_rosters.StaffRoleForm, rosters_forms.StaffRoleForm)

    def test_views_are_reexported(self):
        self.assertIs(vid_views_rosters.roster_overview, rosters_views.roster_overview)
        self.assertIs(vid_views_rosters.person_list, rosters_views.person_list)
        self.assertIs(vid_views_rosters.person_detail, rosters_views.person_detail)
        self.assertIs(vid_views_rosters.person_create, rosters_views.person_create)
        self.assertIs(vid_views_rosters.person_edit, rosters_views.person_edit)
        self.assertIs(vid_views_rosters.player_role_create, rosters_views.player_role_create)
        self.assertIs(vid_views_rosters.staff_role_create, rosters_views.staff_role_create)
        self.assertIs(vid_views_rosters.player_role_edit, rosters_views.player_role_edit)
        self.assertIs(vid_views_rosters.staff_role_edit, rosters_views.staff_role_edit)
        self.assertIs(vid_views_rosters.player_role_toggle_active, rosters_views.player_role_toggle_active)
        self.assertIs(vid_views_rosters.staff_role_toggle_active, rosters_views.staff_role_toggle_active)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class RosterViewUrlTests(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.club = Club.objects.create(
            official_name='Club Voleibol Test',
            federation_id='CLUB-TEST',
        )
        self.org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            club=self.club,
            club_team_names={'1': 'Test Club'},
            is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True
        )
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior',
            category=self.category,
            club=self.club,
            federation_id='TEAM-TEST-1',
            is_active=True,
        )
        self.person = Person.objects.create(
            first_name='Laura',
            last_name='García',
        )
        self.player_role = PlayerRole.objects.create(
            person=self.person,
            team=self.team,
            season=Season.objects.resolve('2025-26'),
            jersey_number=7,
            position='setter',
            is_active=True,
        )

    def test_rosters_roster_overview_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('rosters:roster_overview')
        self.assertEqual(url, '/rosters/plantillas/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plantillas')

    def test_rosters_person_list_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('rosters:person_list')
        self.assertEqual(url, '/rosters/personas/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Laura')

    def test_person_edit_denied_to_is_staff_without_tenant_manager_role(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        staff_user = User.objects.create_user(username='staff_member', password='pass', is_staff=True)
        Membership.objects.create(user=staff_user, organization=self.org, role='member', is_approved=True)

        self.client.force_login(staff_user)
        url = reverse('rosters:person_edit', kwargs={'person_id': self.person.id})
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        # Redirige a person_detail porque no tiene permisos
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('rosters:person_detail', kwargs={'person_id': self.person.id}), response.url)

    def test_person_edit_allowed_to_tenant_manager(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_user = User.objects.create_user(username='club_manager', password='pass')
        Membership.objects.create(user=manager_user, organization=self.org, role='manager', is_approved=True)

        self.client.force_login(manager_user)
        url = reverse('rosters:person_edit', kwargs={'person_id': self.person.id})
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)

    def test_player_role_toggle_active_denied_to_is_staff_regular_member(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        staff_user = User.objects.create_user(username='staff_reg', password='pass', is_staff=True)
        Membership.objects.create(user=staff_user, organization=self.org, role='member', is_approved=True)

        self.client.force_login(staff_user)
        url = reverse('rosters:player_role_toggle_active', kwargs={'role_id': self.player_role.id})
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

    def test_player_role_toggle_active_allowed_to_tenant_manager(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_user = User.objects.create_user(username='mgr_toggle', password='pass')
        Membership.objects.create(user=manager_user, organization=self.org, role='manager', is_approved=True)

        self.client.force_login(manager_user)
        url = reverse('rosters:player_role_toggle_active', kwargs={'role_id': self.player_role.id})
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_cross_tenant_person_edit_denied_with_404(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_user = User.objects.create_user(username='club_a_manager', password='pass')
        Membership.objects.create(user=manager_user, organization=self.org, role='manager', is_approved=True)

        club_b = Club.objects.create(official_name='Club B', federation_id='CLUB-B')
        team_b = Team.objects.create(name='Club B Senior', club=club_b, federation_id='TEAM-B-1', is_active=True)
        person_b = Person.objects.create(first_name='Marta', last_name='Navarro')
        PlayerRole.objects.create(
            person=person_b,
            team=team_b,
            season=Season.objects.resolve('2025-26'),
            jersey_number=10,
            is_active=True,
        )

        self.assertFalse(manager_user.can_edit_person(person_b, tenant=self.org))

        self.client.force_login(manager_user)
        url = reverse('rosters:person_edit', kwargs={'person_id': person_b.id})
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_cross_tenant_player_role_toggle_active_denied_with_404(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_user = User.objects.create_user(username='club_a_manager_toggle', password='pass')
        Membership.objects.create(user=manager_user, organization=self.org, role='manager', is_approved=True)

        club_b = Club.objects.create(official_name='Club B', federation_id='CLUB-B-TOGGLE')
        team_b = Team.objects.create(name='Club B Senior', club=club_b, federation_id='TEAM-B-2', is_active=True)
        person_b = Person.objects.create(first_name='Carla', last_name='Sanz')
        role_b = PlayerRole.objects.create(
            person=person_b,
            team=team_b,
            season=Season.objects.resolve('2025-26'),
            jersey_number=5,
            is_active=True,
        )

        self.client.force_login(manager_user)
        url = reverse('rosters:player_role_toggle_active', kwargs={'role_id': role_b.id})
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_cross_tenant_person_detail_denied_with_404(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_user = User.objects.create_user(username='club_a_manager_detail', password='pass')
        Membership.objects.create(user=manager_user, organization=self.org, role='manager', is_approved=True)

        club_b = Club.objects.create(official_name='Club B', federation_id='CLUB-B-DETAIL')
        team_b = Team.objects.create(name='Club B Senior', club=club_b, federation_id='TEAM-B-3', is_active=True)
        person_b = Person.objects.create(first_name='Elena', last_name='Marin')
        PlayerRole.objects.create(
            person=person_b,
            team=team_b,
            season=Season.objects.resolve('2025-26'),
            jersey_number=3,
            is_active=True,
        )

        self.client.force_login(manager_user)
        url = reverse('rosters:person_detail', kwargs={'person_id': person_b.id})
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_orphan_person_without_roles_denied_to_tenant_manager(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_user = User.objects.create_user(username='orphan_mgr', password='pass')
        Membership.objects.create(user=manager_user, organization=self.org, role='manager', is_approved=True)

        # Ficha huérfana sin roles ni usuario vinculado
        orphan_person = Person.objects.create(first_name='Ficha', last_name='Huerfana')

        # No debe pertenecer a self.org y no debe ser editable por el manager
        self.assertFalse(manager_user.can_edit_person(orphan_person, tenant=self.org))

        self.client.force_login(manager_user)
        url_edit = reverse('rosters:person_edit', kwargs={'person_id': orphan_person.id})
        response_edit = self.client.get(url_edit, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response_edit.status_code, 404)

        url_detail = reverse('rosters:person_detail', kwargs={'person_id': orphan_person.id})
        response_detail = self.client.get(url_detail, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response_detail.status_code, 404)

    def test_orphan_team_without_club_denied_access(self):
        from ilovevoley.core.tenant_utils import team_belongs_to_tenant
        orphan_team = Team.objects.create(
            name='Test Club Huérfano',
            club=None,
            federation_id='TEAM-ORPHAN-1',
            is_active=True,
        )
        self.assertFalse(team_belongs_to_tenant(orphan_team, self.org))



