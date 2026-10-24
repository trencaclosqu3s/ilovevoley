from unittest import mock

from django.test import SimpleTestCase, override_settings

from ilovevoley.core.email_utils import _send_notification_email


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
