import base64
from datetime import date
import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone
from PIL import Image

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.competitions.models import League, Match, MatchLineup
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos.forms import rosters as vid_forms_rosters
from ilovevoley.videos.views import rosters as vid_views_rosters


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class RostersReExportCompatibilityTest(TestCase):
    """La capa de compatibilidad de ``videos`` conserva formularios y vistas históricas."""

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
            federation_id='REEXPORT-R1', is_active=True,
        )

    def test_legacy_form_import_creates_a_person(self):
        form = vid_forms_rosters.PersonForm(
            {'first_name': 'Legacy', 'last_name': 'Ficha', 'birth_year': '2012'},
        )
        self.assertTrue(form.is_valid())
        person = form.save()
        self.assertEqual(person.birth_year, 2012)

    def test_legacy_views_resolve_to_the_canonical_roster_urls(self):
        routes = [
            ('roster_overview', 'rosters:roster_overview', []),
            ('person_list', 'rosters:person_list', []),
            ('person_detail', 'rosters:person_detail', [1]),
            ('person_create', 'rosters:person_create', []),
            ('person_edit', 'rosters:person_edit', [1]),
            ('player_role_create', 'rosters:player_role_create', [1]),
            ('staff_role_create', 'rosters:staff_role_create', [1]),
            ('player_role_edit', 'rosters:player_role_edit', [1]),
            ('staff_role_edit', 'rosters:staff_role_edit', [1]),
            ('player_role_toggle_active', 'rosters:player_role_toggle_active', [1]),
            ('staff_role_toggle_active', 'rosters:staff_role_toggle_active', [1]),
        ]
        for attr, route, args in routes:
            with self.subTest(view=attr):
                legacy_view = getattr(vid_views_rosters, attr)
                self.assertIs(resolve(reverse(route, args=args)).func, legacy_view)

    def test_legacy_roster_overview_renders_the_tenant_teams(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('rosters:roster_overview'), HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.resolver_match.func, vid_views_rosters.roster_overview)
        self.assertIn(self.team, response.context['teams'])


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
        self.person = Person.objects.create(first_name='Laura', last_name='García')
        self.person.organizations.add(self.org)
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
        self.assertIn(self.team, response.context['teams'])
        self.assertEqual(response.context['total_stats']['total_teams'], 1)
        self.assertEqual(response.context['total_stats']['total_players'], 1)

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
            user=self.user, organization=self.org, is_approved=True, role='manager'
        )
        self.client.force_login(self.user)

    def _post(self, photo_payload):
        return self.client.post(
            reverse('rosters:person_create'),
            {
                'first_name': 'Ana',
                'last_name': 'Pérez',
                'birth_year': 2012,
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
        self.manager = User.objects.create_user(username='manager-a', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org_a, is_approved=True, role='manager',
        )
        self.person_a = Person.objects.create(first_name='Ana', last_name='Propia')
        self.person_a.organizations.add(self.org_a)
        self.person_b = Person.objects.create(first_name='Bea', last_name='Ajena')
        self.person_b.organizations.add(self.org_b)
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

    def test_my_profile_agrega_roles_de_todos_los_clubes_por_temporada(self):
        # #340: la ficha vinculada es de otro club (B) y el usuario entra por A.
        self.person_b.user = self.member
        self.person_b.save()
        PlayerRole.objects.create(
            person=self.person_b, team=self.team_b,
            season=Season.objects.resolve('2025-26'), position='setter',
        )
        PlayerRole.objects.create(
            person=self.person_b, team=self.team_a,
            season=Season.objects.resolve('2026-27'), position='opposite',
        )
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('rosters:my_profile'), HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Club B Junior')
        self.assertContains(response, 'Club A Senior')
        self.assertEqual(
            [e['season'].name for e in response.context['seasons']],
            ['2026-27', '2025-26'],
        )

    def test_ficha_de_otro_club_es_visible_donde_tiene_rol_y_oculta_contacto(self):
        # Marc: ficha vinculada al club B, con rol en un equipo del club A.
        self.person_b.email = 'bea@example.com'
        self.person_b.phone = '600000000'
        self.person_b.notes = 'nota privada'
        self.person_b.save()
        PlayerRole.objects.create(
            person=self.person_b, team=self.team_a,
            season=Season.objects.resolve('2026-27'),
        )
        url = reverse('rosters:person_detail', args=[self.person_b.id])

        self.client.force_login(self.member)
        response = self.client.get(url, HTTP_HOST='club-a.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'bea@example.com')
        self.assertNotContains(response, '600000000')
        self.assertNotContains(response, 'nota privada')

        self.client.force_login(self.manager)
        response = self.client.get(url, HTTP_HOST='club-a.ilovevoley.es')
        self.assertContains(response, 'bea@example.com')

    def test_manager_crea_rol_de_jugador_en_la_temporada_elegida(self):
        # #344: el formulario no pintaba `season` (obligatorio) y el alta
        # fallaba en silencio. Debe poder prepararse la temporada siguiente.
        season = Season.objects.resolve('2026-27')
        self.client.force_login(self.manager)
        url = reverse('rosters:player_role_create', args=[self.person_a.id])
        response = self.client.get(url, HTTP_HOST='club-a.ilovevoley.es')
        self.assertContains(response, 'name="season"')

        response = self.client.post(
            url, {'team': self.team_a.id, 'season': season.id, 'jersey_number': 9},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PlayerRole.objects.filter(person=self.person_a, team=self.team_a, season=season).exists(),
        )

    def test_basic_member_cannot_access_person_create(self):
        self.client.force_login(self.member)
        url = reverse('rosters:person_create')
        response_get = self.client.get(url, HTTP_HOST='club-a.ilovevoley.es')
        self.assertEqual(response_get.status_code, 403)

        response_post = self.client.post(
            url,
            {'first_name': 'Invalido', 'last_name': 'Miembro'},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response_post.status_code, 403)

    def test_basic_member_cannot_manage_roles(self):
        """Los roles deportivos exigen manager: un member no puede crear/editar/togglear (#90)."""
        role = PlayerRole.objects.filter(person=self.person_a, team=self.team_a).first()
        staff_role = StaffRole.objects.create(
            person=self.person_a, team=self.team_a, season=role.season, role='head_coach',
        )
        self.client.force_login(self.member)
        cases = [
            ('create_player', 'rosters:player_role_create', [self.person_a.id]),
            ('create_staff', 'rosters:staff_role_create', [self.person_a.id]),
            ('edit_player', 'rosters:player_role_edit', [role.id]),
            ('edit_staff', 'rosters:staff_role_edit', [staff_role.id]),
            ('toggle_player', 'rosters:player_role_toggle_active', [role.id]),
            ('toggle_staff', 'rosters:staff_role_toggle_active', [staff_role.id]),
        ]
        for label, name, args in cases:
            with self.subTest(endpoint=label):
                response = self.client.post(
                    reverse(name, args=args), HTTP_HOST='club-a.ilovevoley.es',
                )
                self.assertEqual(response.status_code, 403)

    def test_alta_duplicada_en_otro_club_se_adopta_en_vez_de_duplicar(self):
        # Identidad global: el club B no crea una segunda Ana, la adopta.
        User = get_user_model()
        from ilovevoley.users.models import Membership
        manager_b = User.objects.create_user(username='manager-b', password='pass')
        Membership.objects.create(
            user=manager_b, organization=self.org_b, is_approved=True, role='manager',
        )
        ana = Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
        )
        ana.organizations.add(self.org_a)
        payload = {'first_name': 'Ana', 'last_name': 'Gomez', 'birth_date': '2010-05-01'}

        self.client.force_login(manager_b)
        response = self.client.post(
            reverse('rosters:person_create'), payload, HTTP_HOST='club-b.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['existing_person'], ana)
        self.assertEqual(Person.objects.filter(first_name='Ana', last_name='Gomez').count(), 1)
        # Aún no es visible en B
        self.assertNotIn(ana, Person.objects.for_tenant(self.org_b))

        response = self.client.post(
            reverse('rosters:person_adopt'),
            {'first_name': 'Ana', 'last_name': 'Gomez', 'birth_year': 2010},
            HTTP_HOST='club-b.ilovevoley.es',
        )
        self.assertRedirects(
            response, reverse('rosters:person_detail', args=[ana.id]),
            fetch_redirect_response=False,
        )
        self.assertIn(ana, Person.objects.for_tenant(self.org_b))
        self.assertIn(ana, Person.objects.for_tenant(self.org_a))

    def test_person_adopt_sin_año_valido_devuelve_404(self):
        # Una ficha sin año no se adopta con solo nombre y apellidos (IS NULL),
        # y un año no numérico no debe dar 500.
        Person.objects.create(first_name='Sin', last_name='Año')
        self.client.force_login(self.manager)
        for year in ('', 'abc', '²'):
            with self.subTest(year=year):
                response = self.client.post(
                    reverse('rosters:person_adopt'),
                    {'first_name': 'Sin', 'last_name': 'Año', 'birth_year': year},
                    HTTP_HOST='club-a.ilovevoley.es',
                )
                self.assertEqual(response.status_code, 404)

    def test_person_adopt_exige_identidad_completa(self):
        # No se adopta por id: sin nombre y año exactos, 404.
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('rosters:person_adopt'),
            {'first_name': 'Bea', 'last_name': 'Ajena', 'birth_year': 1999},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_person_create_ignora_organizaciones_enviadas_por_cliente(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('rosters:person_create'),
            {'first_name': 'Nueva', 'last_name': 'Ficha', 'birth_year': 2012, 'organizations': self.org_b.id},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        created = Person.objects.get(first_name='Nueva', last_name='Ficha')
        self.assertEqual(set(created.organizations.all()), {self.org_a})

    def test_person_list_add_button_visibility_for_tenant_manager(self):
        url = reverse('rosters:person_list')
        create_url = reverse('rosters:person_create')

        self.client.force_login(self.member)
        response = self.client.get(url, HTTP_HOST='club-a.ilovevoley.es')
        self.assertNotContains(response, create_url)
        response_empty = self.client.get(f'{url}?search=inexistente', HTTP_HOST='club-a.ilovevoley.es')
        self.assertNotContains(response_empty, create_url)

        self.client.force_login(self.manager)
        response = self.client.get(url, HTTP_HOST='club-a.ilovevoley.es')
        self.assertContains(response, create_url)
        response_empty = self.client.get(f'{url}?search=inexistente', HTTP_HOST='club-a.ilovevoley.es')
        self.assertContains(response_empty, create_url)

    def test_person_edit_ignora_organizaciones_enviadas_por_cliente(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('rosters:person_edit', args=[self.person_a.id]),
            {'first_name': 'Ana', 'last_name': 'Propia', 'birth_year': 2012, 'organizations': self.org_b.id},
            HTTP_HOST='club-a.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.person_a.refresh_from_db()
        self.assertEqual(set(self.person_a.organizations.all()), {self.org_a})

    def test_staff_global_sin_membresia_no_accede_a_editar_en_otro_club(self):
        # El decorador de tenant corta al no tener membresía aprobada en B.
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('rosters:person_edit', args=[self.person_b.id]),
            HTTP_HOST='club-b.ilovevoley.es',
        )
        self.assertNotEqual(response.status_code, 200)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class PersonDetailStatsTests(TestCase):
    """Las estadísticas de la ficha salen de las actas y respetan el tenant."""

    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club,
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member_stats', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)

        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category,
            club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival', category=self.category, federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Liga', federation_id='L-1', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.person = Person.objects.create(first_name='Laura', last_name='García')
        self.person.organizations.add(self.org)
        PlayerRole.objects.create(
            person=self.person, team=self.team, season=self.season,
            jersey_number=7, is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
        )

    def _lineup(self, team, person, **kwargs):
        defaults = dict(
            match=self.match, team=team, person=person, jersey_number=7,
            is_convocado=True, sets_played=0, sets_started=0,
        )
        defaults.update(kwargs)
        return MatchLineup.objects.create(**defaults)

    def test_person_detail_muestra_las_estadisticas(self):
        self._lineup(self.team, self.person, sets_played=3, sets_started=2)
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('rosters:person_detail', args=[self.person.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['player_stats']['sets_disputados'], 3)
        self.assertEqual(response.context['player_stats']['titularidades'], 1)
        self.assertContains(response, 'Sets disputados')

    def test_person_detail_no_cuenta_equipos_fuera_del_tenant(self):
        self._lineup(self.team, self.person, sets_played=3, sets_started=3)
        equipo_ajeno = Team.objects.create(
            name='Ajeno', category=self.category, federation_id='TEAM-3', is_active=True,
        )
        self._lineup(equipo_ajeno, self.person, sets_played=5, sets_started=5)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('rosters:person_detail', args=[self.person.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.context['player_stats']['sets_disputados'], 3)

    def test_person_detail_sin_actas_no_muestra_el_bloque(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('rosters:person_detail', args=[self.person.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['player_stats'])
        self.assertNotContains(response, 'Sets disputados')
