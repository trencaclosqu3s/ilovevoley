import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from ilovevoley.content.models import Image
from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

HOST = 'testclub.ilovevoley.es'


@override_settings(
    ALLOWED_HOSTS=['testclub.ilovevoley.es', 'otherclub.ilovevoley.es', 'localhost'],
    PROTECTED_MEDIA_USE_X_ACCEL=True,
)
class ProtectedMediaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.other_org = Organization.objects.create(
            slug='otherclub', name='Other Club', is_active=True
        )
        User = get_user_model()
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.member, organization=self.org, is_approved=True)
        self.staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        Membership.objects.create(user=self.staff, organization=self.org, is_approved=True)
        self.season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)

        self.approved = Image.objects.create(
            image='images/2025/06/approved.jpg', title='aprobada',
            uploaded_by=self.member, organization=self.org, status='approved', season=self.season,
        )
        self.pending = Image.objects.create(
            image='images/2025/06/pending.jpg', title='pendiente',
            uploaded_by=self.staff, organization=self.org, status='pending', season=self.season,
        )
        self.foreign = Image.objects.create(
            image='images/2025/06/foreign.jpg', title='ajena',
            uploaded_by=self.staff, organization=self.other_org, status='approved',
            season=self.season,
        )

    def test_anonymous_pending_image_is_forbidden(self):
        response = self.client.get('/media/images/2025/06/pending.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_approved_image_is_forbidden(self):
        response = self.client.get('/media/images/2025/06/approved.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 403)

    def test_member_gets_approved_image_via_x_accel(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/images/2025/06/approved.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['X-Accel-Redirect'], '/protected-media/images/2025/06/approved.jpg'
        )
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_member_cannot_see_pending_image(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/images/2025/06/pending.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 403)

    def test_staff_can_see_pending_image(self):
        self.client.force_login(self.staff)
        response = self.client.get('/media/images/2025/06/pending.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)

    def test_uploader_can_see_own_pending_image(self):
        Image.objects.create(
            image='images/2025/06/mine.jpg', title='mía',
            uploaded_by=self.member, organization=self.org, status='pending', season=self.season,
        )
        self.client.force_login(self.member)
        response = self.client.get('/media/images/2025/06/mine.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_see_other_tenant_image(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/images/2025/06/foreign.jpg', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 404)

    def test_unknown_prefix_is_denied(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/secret.txt', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 404)

    def test_path_traversal_is_denied(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/images/../secret.txt', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 404)

    def test_public_prefix_is_not_served_by_django(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/organizations/logos/logo.png', HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 404)


@override_settings(
    ALLOWED_HOSTS=['testclub.ilovevoley.es', 'noclub.ilovevoley.es', 'localhost'],
    PROTECTED_MEDIA_USE_X_ACCEL=True,
)
class ProtectedPersonMediaTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.club = Club.objects.create(federation_id='club-1', official_name='Club Uno')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True, club=self.club
        )
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.member, organization=self.org, is_approved=True)
        self.season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)

        self.team = Team.objects.create(name='Senior', federation_id='team-1', club=self.club)
        self.person = Person.objects.create(
            first_name='Ana', last_name='Garcia', photo='people/ana_1.jpg'
        )
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.season)

        other_club = Club.objects.create(federation_id='club-2', official_name='Club Dos')
        other_team = Team.objects.create(name='Otro', federation_id='team-2', club=other_club)
        self.foreign_person = Person.objects.create(
            first_name='Luis', last_name='Perez', photo='people/luis_2.jpg'
        )
        PlayerRole.objects.create(person=self.foreign_person, team=other_team, season=self.season)

        noclub_org = Organization.objects.create(slug='noclub', name='Sin Club')
        self.noclub_member = User.objects.create_user(username='noclub', password='pass')
        Membership.objects.create(
            user=self.noclub_member, organization=noclub_org, is_approved=True
        )

    def test_member_can_see_person_of_linked_club(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/people/ana_1.jpg', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Redirect'], '/protected-media/people/ana_1.jpg')

    def test_member_cannot_see_person_of_other_club(self):
        self.client.force_login(self.member)
        response = self.client.get('/media/people/luis_2.jpg', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_anonymous_person_photo_is_forbidden(self):
        response = self.client.get('/media/people/ana_1.jpg', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

    def test_tenant_without_club_cannot_see_person_with_roles(self):
        self.client.force_login(self.noclub_member)
        response = self.client.get('/media/people/ana_1.jpg', HTTP_HOST='noclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_tenant_without_club_can_see_person_without_roles(self):
        Person.objects.create(first_name='Sin', last_name='Rol', photo='people/sinrol_1.jpg')
        self.client.force_login(self.noclub_member)
        response = self.client.get('/media/people/sinrol_1.jpg', HTTP_HOST='noclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)


class PublicMediaDevTests(TestCase):
    """Sin X-Accel (desarrollo) los medios públicos se sirven sin autenticación."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        logo_dir = Path(self.tmp.name) / 'organizations' / 'logos'
        logo_dir.mkdir(parents=True)
        (logo_dir / 'logo.png').write_bytes(b'\x89PNG\r\n\x1a\n')

    def test_public_logo_served_anonymously_in_dev(self):
        with override_settings(MEDIA_ROOT=self.tmp.name, PROTECTED_MEDIA_USE_X_ACCEL=False):
            response = self.client.get('/media/organizations/logos/logo.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

