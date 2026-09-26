import base64
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters import forms as rosters_forms
from ilovevoley.rosters import views as rosters_views
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos.forms import rosters as vid_forms_rosters
from ilovevoley.videos.views import rosters as vid_views_rosters


class RostersReExportCompatibilityTest(SimpleTestCase):
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
            organization=self.org,
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


def _png_data_uri():
    buffer = BytesIO()
    Image.new('RGB', (8, 8), (10, 120, 200)).save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f'data:image/png;base64,{encoded}'


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class PersonPhotoUploadSecurityTests(TestCase):
    """La foto recortada debe ser una imagen real y guardarse siempre como .jpg."""

    def setUp(self):
        from ilovevoley.users.models import Membership

        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

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
        self.client.force_login(self.user)

    def _post(self, photo_payload):
        return self.client.post(
            reverse('rosters:person_create'),
            {
                'first_name': 'Ana',
                'last_name': 'Pérez',
                'cropped_photo_data': photo_payload,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )

    def test_html_injected_as_photo_is_not_stored(self):
        payload = base64.b64encode(b'<script>alert(document.domain)</script>').decode()

        response = self._post(f'data:image/html;base64,{payload}')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Person.objects.filter(first_name='Ana').exists())

    def test_valid_photo_is_stored_as_jpg(self):
        response = self._post(_png_data_uri())

        self.assertEqual(response.status_code, 302)
        person = Person.objects.get(first_name='Ana')
        self.assertTrue(person.photo.name.startswith('people/'))
        self.assertTrue(person.photo.name.endswith('.jpg'))
        with Image.open(person.photo.path) as image:
            self.assertEqual(image.format, 'JPEG')


@override_settings(ALLOWED_HOSTS=['club-a.ilovevoley.es', 'club-b.ilovevoley.es', 'localhost'])
class RostersTenantIsolationTests(TestCase):
    """Las fichas y roles quedan aislados por organización del tenant activo."""

    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org_a = Organization.objects.create(
            slug='club-a', name='Club A', club_team_names={'1': 'Club A'}, is_active=True,
        )
        self.org_b = Organization.objects.create(
            slug='club-b', name='Club B', club_team_names={'1': 'Club B'}, is_active=True,
        )
        User = get_user_model()
        self.member = User.objects.create_user(username='member-a', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org_a, is_approved=True,
        )
        self.staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        Membership.objects.create(
            user=self.staff, organization=self.org_a, is_approved=True, role='manager',
        )
        self.person_a = Person.objects.create(
            first_name='Ana', last_name='Propia', organization=self.org_a,
        )
        self.person_b = Person.objects.create(
            first_name='Bea', last_name='Ajena', organization=self.org_b,
        )
        season = Season.objects.resolve('2025-26')
        self.team_a = Team.objects.create(
            name='Club A Senior', federation_id='TEAM-A1', is_active=True,
        )
        self.team_b = Team.objects.create(
            name='Club B Junior', federation_id='TEAM-B1', is_active=True,
        )
        PlayerRole.objects.create(
            person=self.person_a, team=self.team_a, season=season, jersey_number=3,
        )
        # Rol cruzado heredado: no debe mostrarse en el tenant A.
        PlayerRole.objects.create(
            person=self.person_a, team=self.team_b, season=season, jersey_number=4,
        )

    def test_person_list_solo_muestra_fichas_del_club(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('rosters:person_list'), HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertContains(response, 'Propia')
        self.assertNotContains(response, 'Ajena')

    def test_person_detail_de_otro_club_devuelve_404(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('rosters:person_detail', args=[self.person_b.id]),
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_person_edit_de_otro_club_devuelve_404(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('rosters:person_edit', args=[self.person_b.id]),
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_player_role_create_de_otro_club_devuelve_404(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('rosters:player_role_create', args=[self.person_b.id]),
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_person_detail_no_muestra_roles_de_otro_club(self):
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('rosters:person_detail', args=[self.person_a.id]),
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Club A Senior')
        self.assertNotContains(response, 'Club B Junior')

    def test_person_create_ignora_organizacion_enviada_por_cliente(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('rosters:person_create'),
            {'first_name': 'Nueva', 'last_name': 'Ficha', 'organization': self.org_b.id},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        created = Person.objects.get(first_name='Nueva', last_name='Ficha')
        self.assertEqual(created.organization, self.org_a)

    def test_person_edit_ignora_organizacion_enviada_por_cliente(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('rosters:person_edit', args=[self.person_a.id]),
            {'first_name': 'Ana', 'last_name': 'Propia', 'organization': self.org_b.id},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.person_a.refresh_from_db()
        self.assertEqual(self.person_a.organization, self.org_a)

    def test_staff_global_sin_membresia_no_edita_otra_organizacion(self):
        # Tiene is_staff y membresía en A, pero ninguna en B.
        self.assertFalse(self.staff.can_edit_person(self.person_b, self.org_b))
        # Y sí puede sobre las fichas de su propia organización.
        self.assertTrue(self.staff.can_edit_person(self.person_a, self.org_a))

    def test_miembro_sin_staff_no_edita_ficha_del_club(self):
        self.assertFalse(self.member.can_edit_person(self.person_a, self.org_a))

    def test_staff_global_con_rol_miembro_no_edita_ficha_del_club(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        staff_member = User.objects.create_user(
            username='staff-member', password='pass', is_staff=True
        )
        Membership.objects.create(
            user=staff_member, organization=self.org_a, role='member', is_approved=True,
        )
        self.assertFalse(staff_member.can_edit_person(self.person_a, self.org_a))

    def test_staff_global_sin_membresia_no_accede_a_editar_en_otro_club(self):
        # El decorador de tenant corta al no tener membresía aprobada en B.
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('rosters:person_edit', args=[self.person_b.id]),
            HTTP_HOST='club-b.ilovevoley.es',
        )
        self.assertNotEqual(response.status_code, 200)
