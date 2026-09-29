"""Solicitud de acceso a un club nuevo desde ``/pending-approval/``.

Un usuario ya aprobado en otro club (o un alta con Google resuelta en el dominio
raíz) llega a un tenant sin ``Membership``. La vista debe registrar la solicitud
pendiente para que el club tenga algo que aprobar; si no, el usuario queda
atrapado para siempre y sin nada visible en el panel de moderación (#244).
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership

HOST = 'tenant-a.ilovevoley.es'


@override_settings(ALLOWED_HOSTS=[HOST])
class PendingApprovalViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(slug='tenant-a', name='Tenant A')

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='outsider', password='pass', parent_info='Padre de prueba',
        )

    def _memberships(self, user=None):
        return Membership.objects.filter(user=user or self.user, organization=self.org)

    def test_existing_user_without_membership_gets_pending_request(self):
        self.user.is_approved = True
        self.user.save(update_fields=['is_approved'])
        self.client.force_login(self.user)

        response = self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)

        self.assertEqual(response.status_code, 200)
        membership = self._memberships().get()
        self.assertEqual(membership.role, 'member')
        self.assertFalse(membership.is_approved)

    def test_second_visit_does_not_duplicate_request(self):
        self.user.is_approved = True
        self.user.save(update_fields=['is_approved'])
        self.client.force_login(self.user)

        self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)
        self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)

        self.assertEqual(self._memberships().count(), 1)

    def test_existing_membership_is_left_untouched(self):
        Membership.objects.create(
            user=self.user, organization=self.org, role='member', is_approved=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('profile'))
        self.assertEqual(self._memberships().count(), 1)
        self.assertTrue(self._memberships().get().is_approved)

    def test_superuser_without_membership_does_not_create_request(self):
        superuser = get_user_model().objects.create_superuser(
            username='root', password='pass',
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('profile'))
        self.assertFalse(self._memberships(superuser).exists())

    def test_new_account_sees_account_created_copy(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)

        html = response.content.decode()
        self.assertIn('Cuenta Pendiente de Aprobación', html)
        self.assertIn('Tu cuenta ha sido creada', html)

    def test_activated_user_joining_club_sees_request_copy(self):
        self.user.is_approved = True
        self.user.save(update_fields=['is_approved'])
        self.client.force_login(self.user)

        response = self.client.get(reverse('pending_approval'), HTTP_HOST=HOST)

        html = response.content.decode()
        self.assertIn('Solicitud Pendiente de Aprobación', html)
        self.assertIn('enviado tu solicitud para unirte a', html)
