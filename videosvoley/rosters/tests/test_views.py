from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from videosvoley.core.models import Category, Organization, Season
from videosvoley.rosters import forms as rosters_forms
from videosvoley.rosters import views as rosters_views
from videosvoley.rosters.models import Person, PlayerRole, StaffRole
from videosvoley.teams.models import Club, Team
from videosvoley.videos.forms import rosters as vid_forms_rosters
from videosvoley.videos.views import rosters as vid_views_rosters


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
        from videosvoley.users.models import Membership
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
