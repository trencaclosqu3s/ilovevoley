"""Solicitud de retirada de fotos por deportistas y familias (#362)."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.content.models import Image, ImageRemovalRequest
from ilovevoley.core.models import Organization
from ilovevoley.rosters.models import Person
from ilovevoley.users.models import Membership

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ImageRemovalRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.org = Organization.objects.create(
            slug='testclub', name='Club A', club_team_names={'1': 'Club A'}, is_active=True,
        )
        self.player = User.objects.create_user(username='player', password='pass')
        self.parent = User.objects.create_user(username='parent', password='pass')
        self.stranger = User.objects.create_user(username='stranger', password='pass')
        self.manager = User.objects.create_user(username='manager', password='pass')
        for user in (self.player, self.parent, self.stranger):
            Membership.objects.create(user=user, organization=self.org, is_approved=True)
        Membership.objects.create(
            user=self.manager, organization=self.org, role='manager', is_approved=True,
        )

        self.person = Person.objects.create(first_name='Lluc', last_name='Puig', user=self.player)
        self.parent.children.add(self.person)

        self.image = Image.objects.create(
            image=SimpleUploadedFile('p.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Foto de Lluc', uploaded_by=self.manager, organization=self.org,
            status='approved',
        )
        self.image.persons.add(self.person)

    def _request_removal(self, user, reason='Quiero que se retire'):
        self.client.force_login(user)
        return self.client.post(
            reverse('content:image_removal_request', args=[self.image.id]),
            {'reason': reason}, HTTP_HOST='testclub.ilovevoley.es',
        )

    def test_family_can_request_removal(self):
        response = self._request_removal(self.parent)
        self.assertEqual(response.status_code, 302)
        removal = ImageRemovalRequest.objects.get()
        self.assertEqual(removal.person, self.person)
        self.assertEqual(removal.requested_by, self.parent)
        self.assertEqual(removal.reason, 'Quiero que se retire')
        self.assertEqual(removal.status, 'pending')

    def test_player_can_request_removal(self):
        response = self._request_removal(self.player)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ImageRemovalRequest.objects.filter(requested_by=self.player).exists())

    def test_unrelated_user_cannot_request_removal(self):
        response = self._request_removal(self.stranger)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ImageRemovalRequest.objects.exists())

    def test_duplicate_pending_request_is_not_created(self):
        self._request_removal(self.parent)
        self._request_removal(self.player)
        self.assertEqual(ImageRemovalRequest.objects.count(), 1)

    def test_manager_removes_image(self):
        self._request_removal(self.parent)
        removal = ImageRemovalRequest.objects.get()

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('core:resolve_image_removal', args=[removal.id]),
            {'action': 'remove'}, HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Image.objects.filter(id=self.image.id).exists())
        removal.refresh_from_db()
        self.assertEqual(removal.status, 'removed')
        self.assertIsNone(removal.image)
        self.assertEqual(removal.resolved_by, self.manager)

    def test_manager_dismisses_request_keeps_image(self):
        self._request_removal(self.parent)
        removal = ImageRemovalRequest.objects.get()

        self.client.force_login(self.manager)
        self.client.post(
            reverse('core:resolve_image_removal', args=[removal.id]),
            {'action': 'dismiss'}, HTTP_HOST='testclub.ilovevoley.es',
        )
        removal.refresh_from_db()
        self.assertEqual(removal.status, 'dismissed')
        self.assertTrue(Image.objects.filter(id=self.image.id).exists())

    def test_non_manager_cannot_resolve(self):
        self._request_removal(self.parent)
        removal = ImageRemovalRequest.objects.get()

        self.client.force_login(self.parent)
        response = self.client.post(
            reverse('core:resolve_image_removal', args=[removal.id]),
            {'action': 'remove'}, HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Image.objects.filter(id=self.image.id).exists())
