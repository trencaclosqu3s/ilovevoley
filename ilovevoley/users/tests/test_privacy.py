from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ilovevoley.users.models import DataExport
from ilovevoley.users.privacy import active_export_for, is_erased


class ExportWindowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='ana', password='pass', email='ana@example.com',
        )

    def test_pending_older_than_one_hour_does_not_block(self):
        old = DataExport.objects.create(user=self.user, status=DataExport.Status.PENDING)
        DataExport.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=2),
        )
        fresh = DataExport.objects.create(
            user=self.user,
            status=DataExport.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.assertEqual(active_export_for(self.user).pk, fresh.pk)
        old.refresh_from_db()
        self.assertEqual(old.status, DataExport.Status.FAILED)

    def test_erased_marker_is_the_deleted_username(self):
        self.assertFalse(is_erased(self.user))
        self.user.username = f'deleted-{self.user.pk}'
        self.assertTrue(is_erased(self.user))
