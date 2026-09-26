import socket
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ilovevoley.core.security import UnsafeURL, safe_get, validate_url

PUBLIC_IP = '93.184.216.34'
ALLOWED = ['federatio.com']


def _addrinfo(ip, port=443):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))]


class ValidateUrlTests(SimpleTestCase):
    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    def test_accepts_subdomain_of_allowed_host(self, _):
        validate_url('https://voleibolib.federatio.com/actas/1/a.html', ALLOWED)

    def test_rejects_non_https_scheme(self):
        with self.assertRaises(UnsafeURL):
            validate_url('http://federatio.com/actas/1/a.html', ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    def test_rejects_host_outside_whitelist(self, _):
        with self.assertRaises(UnsafeURL):
            validate_url('https://evil.example.com/actas/1/a.html', ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    def test_rejects_suffix_lookalike_host(self, _):
        for url in ('https://notfederatio.com/x', 'https://federatio.com.evil.example.com/x'):
            with self.assertRaises(UnsafeURL):
                validate_url(url, ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo('127.0.0.1'))
    def test_rejects_loopback_resolution(self, _):
        with self.assertRaises(UnsafeURL):
            validate_url('https://federatio.com/x', ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo('10.0.0.5'))
    def test_rejects_private_resolution(self, _):
        with self.assertRaises(UnsafeURL):
            validate_url('https://federatio.com/x', ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo')
    def test_rejects_when_any_resolved_ip_is_private(self, mock_dns):
        mock_dns.return_value = _addrinfo(PUBLIC_IP) + _addrinfo('169.254.169.254')
        with self.assertRaises(UnsafeURL):
            validate_url('https://federatio.com/x', ALLOWED)


class SafeGetTests(SimpleTestCase):
    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    @patch('ilovevoley.core.security.requests.get')
    def test_returns_content_without_following_redirects(self, mock_get, _):
        response = MagicMock()
        response.is_redirect = False
        response.iter_content.return_value = [b'<html>ok</html>']
        mock_get.return_value = response

        content = safe_get('https://federatio.com/x', allowed_hosts=ALLOWED)

        self.assertEqual(content, b'<html>ok</html>')
        self.assertFalse(mock_get.call_args.kwargs['allow_redirects'])
        self.assertTrue(mock_get.call_args.kwargs['stream'])
        response.raise_for_status.assert_called_once()

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    @patch('ilovevoley.core.security.requests.get')
    def test_rejects_redirect_response(self, mock_get, _):
        response = MagicMock()
        response.is_redirect = True
        mock_get.return_value = response

        with self.assertRaises(UnsafeURL):
            safe_get('https://federatio.com/x', allowed_hosts=ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    @patch('ilovevoley.core.security.requests.get')
    def test_rejects_payload_over_max_bytes(self, mock_get, _):
        response = MagicMock()
        response.is_redirect = False
        response.iter_content.return_value = [b'a' * 10, b'b' * 10]
        mock_get.return_value = response

        with self.assertRaises(UnsafeURL):
            safe_get('https://federatio.com/x', allowed_hosts=ALLOWED, max_bytes=15)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo('10.0.0.5'))
    @patch('ilovevoley.core.security.requests.get')
    def test_does_not_request_when_ip_is_private(self, mock_get, _):
        with self.assertRaises(UnsafeURL):
            safe_get('https://federatio.com/x', allowed_hosts=ALLOWED)

        mock_get.assert_not_called()
