from unittest import mock

from django.test import SimpleTestCase, override_settings

from ilovevoley.core.email_utils import _send_notification_email, send_technical_alert


class SendNotificationEmailFailureTest(SimpleTestCase):
    @override_settings(NOTIFICATION_EMAIL_ENABLED=True, EMAIL_HOST_USER='noreply@example.com')
    def test_smtp_failure_is_logged_not_swallowed(self):
        # Un fallo SMTP debe llegar a logging (y por tanto a Sentry), no solo a stdout.
        with mock.patch('ilovevoley.core.email_utils.render_to_string', return_value='<p>x</p>'), \
                mock.patch('ilovevoley.core.email_utils.send_mail', side_effect=OSError('smtp down')):
            with self.assertLogs('ilovevoley.core.email_utils', level='ERROR') as logs:
                sent = _send_notification_email('Asunto', 'tpl.html', {}, recipient_list=['a@b.com'])

        self.assertFalse(sent)
        self.assertIn('Asunto', logs.output[0])


class SendTechnicalAlertTest(SimpleTestCase):
    @override_settings(
        NOTIFICATION_EMAIL_ENABLED=True,
        TECHNICAL_ALERT_EMAILS=['tech@example.com'],
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    def test_sends_to_technical_alert_recipients(self):
        with mock.patch('ilovevoley.core.email_utils.send_mail') as mock_send:
            sent = send_technical_alert('Alerta scraping', 'Detalles del error')

        self.assertTrue(sent)
        mock_send.assert_called_once_with(
            subject='Alerta scraping',
            message='Detalles del error',
            from_email='noreply@example.com',
            recipient_list=['tech@example.com'],
            fail_silently=False,
        )

    @override_settings(NOTIFICATION_EMAIL_ENABLED=False)
    def test_does_not_send_when_notifications_disabled(self):
        with mock.patch('ilovevoley.core.email_utils.send_mail') as mock_send:
            sent = send_technical_alert('Alerta scraping', 'Detalles')

        self.assertFalse(sent)
        mock_send.assert_not_called()

    @override_settings(
        NOTIFICATION_EMAIL_ENABLED=True,
        TECHNICAL_ALERT_EMAILS=['tech@example.com'],
    )
    def test_smtp_failure_is_logged_and_returns_false(self):
        with mock.patch('ilovevoley.core.email_utils.send_mail', side_effect=OSError('smtp error')):
            with self.assertLogs('ilovevoley.core.email_utils', level='ERROR') as logs:
                sent = send_technical_alert('Alerta scraping', 'Detalles')

        self.assertFalse(sent)
        self.assertIn('Alerta scraping', logs.output[0])
