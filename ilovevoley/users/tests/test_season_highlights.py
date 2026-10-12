"""Mail puntual de novedades de temporada: destinatarios y envío."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership
from ilovevoley.users.season_highlights import (
    season_highlights_recipients,
    send_season_highlights_email,
)

User = get_user_model()


class SeasonHighlightsRecipientsTests(TestCase):
    """Solo activos aprobados con email; no pendientes ni sin correo."""

    def setUp(self):
        self.org = Organization.objects.create(slug='clubmail', name='Club Mail')
        self.ok = User.objects.create_user(
            username='ok', email='ok@example.com', password='x',
            is_approved=True, is_active=True,
        )
        Membership.objects.create(
            user=self.ok, organization=self.org, role='member', is_approved=True,
        )
        self.pending = User.objects.create_user(
            username='pend', email='pend@example.com', password='x',
            is_approved=False, is_active=True,
        )
        self.no_email = User.objects.create_user(
            username='noem', email='', password='x',
            is_approved=True, is_active=True,
        )
        self.inactive = User.objects.create_user(
            username='ina', email='ina@example.com', password='x',
            is_approved=True, is_active=False,
        )

    def test_recipients_only_active_approved_with_email(self):
        emails = set(season_highlights_recipients().values_list('email', flat=True))
        self.assertEqual(emails, {'ok@example.com'})


class SeasonHighlightsSendTests(TestCase):
    """El envío personaliza URL de avisos y token de baja voluntaria."""

    def setUp(self):
        self.org = Organization.objects.create(slug='clubsend', name='Club Send')
        self.user = User.objects.create_user(
            username='sendme', email='sendme@example.com', password='x',
            is_approved=True, is_active=True,
        )
        Membership.objects.create(
            user=self.user, organization=self.org, role='member', is_approved=True,
        )

    @mock.patch('ilovevoley.users.season_highlights.send_notification_email', return_value=True)
    def test_send_builds_avisos_and_deactivation_urls(self, mocked_send):
        self.assertTrue(send_season_highlights_email(self.user))
        mocked_send.assert_called_once()
        kwargs = mocked_send.call_args.kwargs
        ctx = kwargs['context']
        self.assertIn('tab=avisos', ctx['avisos_url'])
        self.assertIn('/deactivate-account/', ctx['deactivation_url'])
        self.assertEqual(kwargs['recipient_list'], ['sendme@example.com'])
