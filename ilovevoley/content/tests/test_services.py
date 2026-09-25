from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from ilovevoley.content.models import Image
from ilovevoley.content.services import moderate_image
from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class ModerateImageServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.org_a = Organization.objects.create(slug='cluba', name='Club A', is_active=True)
        self.org_b = Organization.objects.create(slug='clubb', name='Club B', is_active=True)

        self.superuser = User.objects.create_superuser(username='super', password='pass')

        self.manager_a = User.objects.create_user(username='manager_a', password='pass')
        Membership.objects.create(
            user=self.manager_a, organization=self.org_a, role='manager', is_approved=True
        )

        self.staff_a = User.objects.create_user(username='staff_a', password='pass', is_staff=True)
        Membership.objects.create(
            user=self.staff_a, organization=self.org_a, role='member', is_approved=True
        )

        self.member_a = User.objects.create_user(username='member_a', password='pass')
        Membership.objects.create(
            user=self.member_a, organization=self.org_a, role='member', is_approved=True
        )

        self.uploader_b = User.objects.create_user(username='uploader_b', password='pass')
        Membership.objects.create(
            user=self.uploader_b, organization=self.org_b, role='member', is_approved=True
        )

        self.image_a = Image.objects.create(
            image=SimpleUploadedFile('test_a.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen Club A',
            uploaded_by=self.manager_a,
            organization=self.org_a,
            status='pending',
        )

        self.image_b = Image.objects.create(
            image=SimpleUploadedFile('test_b.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen Club B',
            uploaded_by=self.uploader_b,
            organization=self.org_b,
            status='pending',
        )

    def test_manager_cannot_moderate_image_from_another_organization(self):
        with self.assertRaises(PermissionDenied):
            moderate_image(
                actor=self.manager_a,
                tenant=self.org_a,
                image=self.image_b,
                decision='approve',
            )
        self.image_b.refresh_from_db()
        self.assertEqual(self.image_b.status, 'pending')

    def test_member_without_manager_or_staff_role_cannot_moderate_image(self):
        with self.assertRaises(PermissionDenied):
            moderate_image(
                actor=self.member_a,
                tenant=self.org_a,
                image=self.image_a,
                decision='approve',
            )
        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.status, 'pending')

    def test_manager_can_approve_image_from_own_organization(self):
        moderate_image(
            actor=self.manager_a,
            tenant=self.org_a,
            image=self.image_a,
            decision='approve',
            notes='Todo correcto',
        )
        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.status, 'approved')
        self.assertEqual(self.image_a.moderated_by, self.manager_a)
        self.assertEqual(self.image_a.moderation_notes, 'Todo correcto')
        self.assertIsNotNone(self.image_a.moderation_date)

    def test_staff_can_reject_image_from_own_organization(self):
        moderate_image(
            actor=self.staff_a,
            tenant=self.org_a,
            image=self.image_a,
            decision='reject',
            notes='Baja calidad',
        )
        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.status, 'rejected')
        self.assertEqual(self.image_a.moderated_by, self.staff_a)
        self.assertEqual(self.image_a.moderation_notes, 'Baja calidad')

    def test_superuser_with_tenant_cannot_moderate_image_from_another_tenant(self):
        with self.assertRaises(PermissionDenied):
            moderate_image(
                actor=self.superuser,
                tenant=self.org_a,
                image=self.image_b,
                decision='approve',
            )
        self.image_b.refresh_from_db()
        self.assertEqual(self.image_b.status, 'pending')

    def test_superuser_without_tenant_can_moderate_any_image(self):
        moderate_image(
            actor=self.superuser,
            tenant=None,
            image=self.image_b,
            decision='approve',
        )
        self.image_b.refresh_from_db()
        self.assertEqual(self.image_b.status, 'approved')

    def test_invalid_decision_raises_value_error(self):
        with self.assertRaises(ValueError):
            moderate_image(
                actor=self.manager_a,
                tenant=self.org_a,
                image=self.image_a,
                decision='invalid_action',
            )

    def test_already_moderated_image_raises_value_error(self):
        self.image_a.status = 'approved'
        self.image_a.save()
        with self.assertRaises(ValueError):
            moderate_image(
                actor=self.manager_a,
                tenant=self.org_a,
                image=self.image_a,
                decision='approve',
            )
