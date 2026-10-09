"""Regresión de acceso cruzado entre tenants (IDOR/BOLA).

Crea dos tenants completos (A y B) y comprueba que un cliente autenticado en A
no alcanza recursos de B en las rutas de detalle y mutación. Los listados y
contadores deben excluir los datos del otro tenant.
"""

from ilovevoley.teams.tests.helpers import identity_of
import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image, Video
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


@override_settings(ALLOWED_HOSTS=['tenant-a.ilovevoley.es', 'tenant-b.ilovevoley.es'])
class CrossTenantAccessTests(TestCase):
    """Un tenant nunca ve ni muta recursos de otro; los listados no filtran datos."""

    HOST_A = 'tenant-a.ilovevoley.es'
    HOST_B = 'tenant-b.ilovevoley.es'

    @classmethod
    def setUpTestData(cls):
        cache.clear()
        User = get_user_model()
        season = Season.objects.resolve('2026-2027')
        cls.category = Category.objects.create(name='Senior', is_active=True)

        cls.club_a = Club.objects.create(federation_id='club-a', official_name='Club A')
        cls.club_b = Club.objects.create(federation_id='club-b', official_name='Club B')
        cls.org_a = Organization.objects.create(
            slug='tenant-a', name='Tenant A', club=cls.club_a,
            club_team_names={'Senior': 'Team A'}, is_active=True,
        )
        cls.org_b = Organization.objects.create(
            slug='tenant-b', name='Tenant B', club=cls.club_b,
            club_team_names={'Senior': 'Team B'}, is_active=True,
        )

        cls.team_a = Team.objects.create(
            name='Team A Senior', federation_id='team-a', club=cls.club_a,
            category=cls.category, is_active=True,
        )
        cls.team_b = Team.objects.create(
            name='Team B Senior', federation_id='team-b', club=cls.club_b,
            category=cls.category, is_active=True,
        )
        # Rival sin club ni nombre de club: no debe colarse en ningún tenant.
        cls.neutral_team = Team.objects.create(
            name='Neutral FC', federation_id='team-neutral', club=None,
            category=cls.category, is_active=True,
        )

        cls.member_a = User.objects.create_user(username='member-a', password='pass')
        Membership.objects.create(
            user=cls.member_a, organization=cls.org_a, is_approved=True, role='member',
        )
        cls.staff_a = User.objects.create_user(username='staff-a', password='pass', is_staff=True)
        Membership.objects.create(
            user=cls.staff_a, organization=cls.org_a, is_approved=True, role='admin',
        )
        cls.manager_a = User.objects.create_user(username='manager-a', password='pass')
        Membership.objects.create(
            user=cls.manager_a, organization=cls.org_a, is_approved=True, role='manager',
        )
        cls.superuser = User.objects.create_superuser(username='root', password='pass')

        cls.user_b = User.objects.create_user(username='member-b', password='pass')
        Membership.objects.create(
            user=cls.user_b, organization=cls.org_b, is_approved=True, role='member',
        )
        cls.pending_a = User.objects.create_user(username='pending-a', password='pass')
        Membership.objects.create(
            user=cls.pending_a, organization=cls.org_a, is_approved=False, role='member',
        )
        cls.pending_b = User.objects.create_user(username='pending-b', password='pass')
        Membership.objects.create(
            user=cls.pending_b, organization=cls.org_b, is_approved=False, role='member',
        )

        cls.league_a = League.objects.create(
            name='Liga A', federation_id='liga-a', season=season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.league_b = League.objects.create(
            name='Liga B', federation_id='liga-b', season=season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.match_a = Match.objects.create(
            league=cls.league_a, home_team=cls.team_a, away_team=cls.neutral_team,
            match_date=timezone.now(), round_number=1, status='scheduled',
        )
        cls.match_b = Match.objects.create(
            league=cls.league_b, home_team=cls.team_b, away_team=cls.neutral_team,
            match_date=timezone.now(), round_number=1, status='scheduled',
        )

        cls.video_a = Video.objects.create(
            title='Video A', youtube_url='https://youtu.be/a',
            created_by=cls.member_a, organization=cls.org_a, season=season,
        )
        cls.video_b = Video.objects.create(
            title='Video B', youtube_url='https://youtu.be/b',
            created_by=cls.user_b, organization=cls.org_b, season=season,
        )

        def make_image(title, owner, org, status):
            return Image.objects.create(
                image=SimpleUploadedFile(f'{title}.jpg', TINY_GIF, content_type='image/jpeg'),
                title=title, uploaded_by=owner, organization=org,
                status=status, season=season,
            )

        cls.image_a = make_image('image-a', cls.member_a, cls.org_a, 'approved')
        cls.image_b = make_image('image-b', cls.user_b, cls.org_b, 'approved')
        cls.pending_image_a = make_image('pending-a', cls.member_a, cls.org_a, 'pending')
        cls.pending_image_b = make_image('pending-b', cls.user_b, cls.org_b, 'pending')

        cls.album_a = uuid4()
        cls.image_a.album_group_id = cls.album_a
        cls.image_a.save(update_fields=['album_group_id'])

        cls.album_b = uuid4()
        cls.image_b.album_group_id = cls.album_b
        cls.image_b.save(update_fields=['album_group_id'])

        cls.person_a = Person.objects.create(
            first_name='Ana', last_name='A',
        )
        cls.person_a.organizations.add(cls.org_a)
        cls.person_b = Person.objects.create(
            first_name='Bea', last_name='B',
        )
        cls.person_b.organizations.add(cls.org_b)
        cls.player_role_a = PlayerRole.objects.create(
            person=cls.person_a, identity=identity_of(cls.team_a), season=season, jersey_number=1,
        )
        cls.player_role_b = PlayerRole.objects.create(
            person=cls.person_b, identity=identity_of(cls.team_b), season=season, jersey_number=1,
        )
        cls.staff_role_a = StaffRole.objects.create(
            person=cls.person_a, identity=identity_of(cls.team_a), season=season, role='head_coach',
        )
        cls.staff_role_b = StaffRole.objects.create(
            person=cls.person_b, identity=identity_of(cls.team_b), season=season, role='head_coach',
        )

    def test_cross_tenant_get_requests_are_blocked(self):
        cases = [
            ('video_detail', self.member_a, reverse('content:video_detail', args=[self.video_b.id])),
            ('image_detail', self.member_a, reverse('content:image_detail', args=[self.image_b.id])),
            ('match_images', self.member_a, reverse('content:match_images', args=[self.match_b.id])),
            ('album_group_images', self.member_a, reverse('content:album_group_images', args=[self.album_b])),
            ('league_detail', self.member_a, reverse('competitions:league_detail', args=[self.league_b.id])),
            ('image_moderate_action', self.staff_a, reverse('content:image_moderate_action', args=[self.pending_image_b.id])),
            ('team_roster', self.member_a, reverse('teams:team_roster', args=[self.team_b.id])),
            ('person_detail', self.member_a, reverse('rosters:person_detail', args=[self.person_b.id])),
            ('person_edit', self.member_a, reverse('rosters:person_edit', args=[self.person_b.id])),
            ('player_role_edit', self.manager_a, reverse('rosters:player_role_edit', args=[self.player_role_b.id])),
            ('staff_role_edit', self.manager_a, reverse('rosters:staff_role_edit', args=[self.staff_role_b.id])),
        ]
        for label, user, url in cases:
            with self.subTest(endpoint=label):
                self.client.force_login(user)
                response = self.client.get(url, HTTP_HOST=self.HOST_A)
                self.assertEqual(response.status_code, 404, f'{label} devolvió {response.status_code}')

    def test_cross_tenant_mutations_are_blocked(self):
        self.client.force_login(self.member_a)
        response = self.client.post(
            reverse('content:video_detail', args=[self.video_b.id]), HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.manager_a)
        response = self.client.post(
            reverse('competitions:ajax_add_match_result', args=[self.match_b.id]),
            data=json.dumps({'home_score': 3, 'away_score': 1}),
            content_type='application/json', HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 404)
        self.match_b.refresh_from_db()
        self.assertIsNone(self.match_b.home_score)
        self.assertEqual(self.match_b.status, 'scheduled')

        self.client.force_login(self.staff_a)
        response = self.client.post(
            reverse('content:image_moderate_action', args=[self.pending_image_b.id]),
            data={'action': 'approve'}, HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 404)
        self.pending_image_b.refresh_from_db()
        self.assertEqual(self.pending_image_b.status, 'pending')

        response = self.client.post(
            reverse('content:image_moderate_bulk'),
            data={'action': 'approve', 'image_ids': [self.pending_image_b.id]},
            HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 302)
        self.pending_image_b.refresh_from_db()
        self.assertEqual(self.pending_image_b.status, 'pending')

        self.client.force_login(self.manager_a)
        for url_name in ('core:approve_user_api', 'core:reject_user_api'):
            with self.subTest(endpoint=url_name):
                response = self.client.post(
                    reverse(url_name, args=[self.pending_b.id]), HTTP_HOST=self.HOST_A,
                )
                self.assertEqual(response.status_code, 404)

        self.client.force_login(self.member_a)
        response = self.client.post(
            reverse('rosters:person_edit', args=[self.person_b.id]),
            data={'first_name': 'Hacked', 'last_name': 'B'}, HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 404)
        self.person_b.refresh_from_db()
        self.assertEqual(self.person_b.first_name, 'Bea')

        # Los roles deportivos exigen manager (PR #200); un manager legítimo de A
        # sigue sin poder tocar los roles de B (404).
        self.client.force_login(self.manager_a)
        response = self.client.post(
            reverse('rosters:player_role_create', args=[self.person_b.id]),
            data={'identity': identity_of(self.team_b).id, 'season': self.player_role_b.season_id},
            HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 404)

        for url_name, role in (
            ('rosters:player_role_toggle_active', self.player_role_b),
            ('rosters:staff_role_toggle_active', self.staff_role_b),
        ):
            with self.subTest(endpoint=url_name):
                response = self.client.post(
                    reverse(url_name, args=[role.id]), HTTP_HOST=self.HOST_A,
                )
                self.assertEqual(response.status_code, 404)
                role.refresh_from_db()
                self.assertTrue(role.is_active)

    def test_ajax_search_teams_scoped_to_tenant(self):
        """El autocompletado de equipos no filtra equipos de otro club (#207)."""
        self.client.force_login(self.manager_a)
        response = self.client.get(
            reverse('competitions:ajax_search_teams'),
            {'q': 'Senior'}, HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        names = {team['name'] for team in response.json()['teams']}
        self.assertIn(self.team_a.name, names)
        self.assertNotIn(self.team_b.name, names)

    def test_ajax_search_teams_rival_mode_is_explicit_and_minimal(self):
        """El modo rival es explícito y devuelve solo id/nombre, sin club (#207)."""
        self.client.force_login(self.manager_a)
        response = self.client.get(
            reverse('competitions:ajax_search_teams'),
            {'q': 'Team', 'scope': 'rival'}, HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        teams = response.json()['teams']
        names = {team['name'] for team in teams}
        self.assertIn(self.team_b.name, names)
        self.assertNotIn(self.team_a.name, names)
        for team in teams:
            self.assertEqual(set(team), {'id', 'name'})

    def test_image_moderation_list_excludes_other_tenant(self):
        self.client.force_login(self.staff_a)
        response = self.client.get(reverse('content:image_moderation'), HTTP_HOST=self.HOST_A)
        self.assertEqual(response.status_code, 200)
        ids = {img.id for img in response.context['page_obj'].object_list}
        self.assertIn(self.pending_image_a.id, ids)
        self.assertNotIn(self.pending_image_b.id, ids)

    def test_moderation_counts_scoped_to_tenant(self):
        self.client.force_login(self.manager_a)
        response = self.client.get(reverse('core:moderation_counts_api'), HTTP_HOST=self.HOST_A)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['pending_users'], 1)

    def test_cross_tenant_match_detail_allows_public_info_but_hides_media(self):
        """El detalle de partido es público (información federativa), pero oculta fotos y vídeos a miembros de otros clubes."""
        self.client.force_login(self.member_a)
        response = self.client.get(
            reverse('competitions:match_detail', args=[self.match_b.id]),
            HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['is_own_match'])
        self.assertEqual(list(response.context['videos']), [])
        self.assertEqual(list(response.context['images']), [])
        self.assertFalse(response.context['can_manage_videos'])
        self.assertFalse(response.context['can_edit_result'])

    def test_cross_tenant_ajax_acta_lineup_accessible_with_person_isolation(self):
        """El acta es pública pero aísla las personas/fichas internas del otro club."""
        self.match_b.acta_html = 'https://voleibolib.federatio.com/acta/123'
        self.match_b.acta_data = {
            'home_team': self.team_b.name,
            'away_team': self.neutral_team.name,
            'home_captain': '1',
            'away_captain': '',
            'home_convocados': ['1 Bea B'],
            'away_convocados': [],
            'sets': [],
        }
        self.match_b.save(update_fields=['acta_html', 'acta_data'])

        # Usuario de org_a consulta acta de partido de org_b: acceso 200, pero sin ficha de Person de org_b
        self.client.force_login(self.member_a)
        response = self.client.get(
            reverse('competitions:ajax_acta_lineup', args=[self.match_b.id]),
            HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        home_players = data['home_convocados']
        self.assertEqual(len(home_players), 1)
        self.assertEqual(home_players[0]['number'], 1)
        self.assertIsNone(home_players[0]['person'])

        # Usuario de org_b consulta su propia acta: sí ve la ficha Person enriquecida
        self.client.force_login(self.user_b)
        response_b = self.client.get(
            reverse('competitions:ajax_acta_lineup', args=[self.match_b.id]),
            HTTP_HOST=self.HOST_B,
        )
        self.assertEqual(response_b.status_code, 200)
        data_b = response_b.json()
        self.assertTrue(data_b['success'])
        self.assertIsNotNone(data_b['home_convocados'][0]['person'])
        self.assertEqual(data_b['home_convocados'][0]['person']['id'], self.person_b.id)

    def test_own_resources_are_accessible(self):
        self.client.force_login(self.member_a)
        cases = [
            ('video_detail', reverse('content:video_detail', args=[self.video_a.id])),
            ('image_detail', reverse('content:image_detail', args=[self.image_a.id])),
            ('album_group_images', reverse('content:album_group_images', args=[self.album_a])),
            ('match_images', reverse('content:match_images', args=[self.match_a.id])),
            ('league_detail', reverse('competitions:league_detail', args=[self.league_a.id])),
            ('match_detail', reverse('competitions:match_detail', args=[self.match_a.id])),
            ('team_roster', reverse('teams:team_roster', args=[self.team_a.id])),
            ('person_detail', reverse('rosters:person_detail', args=[self.person_a.id])),
        ]
        for label, url in cases:
            with self.subTest(endpoint=label):
                response = self.client.get(url, HTTP_HOST=self.HOST_A)
                self.assertEqual(response.status_code, 200, f'{label} devolvió {response.status_code}')

    def test_manager_can_update_own_match_result(self):
        self.client.force_login(self.manager_a)
        response = self.client.post(
            reverse('competitions:ajax_add_match_result', args=[self.match_a.id]),
            data=json.dumps({'home_score': 3, 'away_score': 1}),
            content_type='application/json', HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.match_a.refresh_from_db()
        self.assertEqual(self.match_a.status, 'finished')

    def test_superuser_bypasses_tenant_filter(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse('content:video_detail', args=[self.video_b.id]), HTTP_HOST=self.HOST_A,
        )
        self.assertEqual(response.status_code, 200)
