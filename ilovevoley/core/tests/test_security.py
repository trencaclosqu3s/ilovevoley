import socket
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ilovevoley.core.security import (
    UnsafeURL,
    _PinnedHTTPSConnection,
    _PinnedHTTPSConnectionPool,
    _PinnedIPAdapter,
    safe_get,
    validate_url,
)

PUBLIC_IP = '93.184.216.34'
ALLOWED = ['federatio.com']


def _addrinfo(ip, port=443):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))]


class ValidateUrlTests(SimpleTestCase):
    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    def test_accepts_subdomain_and_returns_pinned_ip(self, _):
        _, ip = validate_url('https://voleibolib.federatio.com/actas/1/a.html', ALLOWED)
        self.assertEqual(ip, PUBLIC_IP)

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

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo('::ffff:127.0.0.1'))
    def test_rejects_ipv4_mapped_loopback(self, _):
        with self.assertRaises(UnsafeURL):
            validate_url('https://federatio.com/x', ALLOWED)


class PinnedConnectionTests(SimpleTestCase):
    def test_adapter_builds_pool_that_pins_ip(self):
        adapter = _PinnedIPAdapter(PUBLIC_IP)
        adapter.init_poolmanager(1, 1)
        pool = adapter.poolmanager.connection_from_url('https://federatio.com/actas/1/a.html')

        self.assertIs(pool.ConnectionCls, _PinnedHTTPSConnectionPool.ConnectionCls)
        self.assertEqual(pool.conn_kw['pinned_ip'], PUBLIC_IP)

    @patch('urllib3.util.connection.create_connection', return_value=MagicMock())
    def test_connection_uses_pinned_ip_but_keeps_hostname(self, mock_create):
        conn = _PinnedHTTPSConnection('federatio.com', 443, pinned_ip=PUBLIC_IP)

        conn._new_conn()

        self.assertEqual(mock_create.call_args.args[0], (PUBLIC_IP, 443))
        self.assertEqual(conn.host, 'federatio.com')
        self.assertEqual(conn._dns_host, 'federatio.com')


class SafeGetTests(SimpleTestCase):
    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    @patch('ilovevoley.core.security.requests.Session')
    def test_pins_validated_ip_and_disables_redirects(self, mock_session_cls, _):
        response = MagicMock()
        response.is_redirect = False
        response.iter_content.return_value = [b'<html>ok</html>']
        session = mock_session_cls.return_value
        session.get.return_value = response

        content = safe_get('https://federatio.com/x', allowed_hosts=ALLOWED)

        self.assertEqual(content, b'<html>ok</html>')
        self.assertTrue(session.trust_env is False)
        mounted = session.mount.call_args.args
        self.assertEqual(mounted[0], 'https://')
        self.assertEqual(mounted[1]._pinned_ip, PUBLIC_IP)
        kwargs = session.get.call_args.kwargs
        self.assertFalse(kwargs['allow_redirects'])
        self.assertTrue(kwargs['stream'])
        response.raise_for_status.assert_called_once()

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    @patch('ilovevoley.core.security.requests.Session')
    def test_rejects_redirect_response(self, mock_session_cls, _):
        response = MagicMock()
        response.is_redirect = True
        session = mock_session_cls.return_value
        session.get.return_value = response

        with self.assertRaises(UnsafeURL):
            safe_get('https://federatio.com/x', allowed_hosts=ALLOWED)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo(PUBLIC_IP))
    @patch('ilovevoley.core.security.requests.Session')
    def test_rejects_payload_over_max_bytes(self, mock_session_cls, _):
        response = MagicMock()
        response.is_redirect = False
        response.iter_content.return_value = [b'a' * 10, b'b' * 10]
        session = mock_session_cls.return_value
        session.get.return_value = response

        with self.assertRaises(UnsafeURL):
            safe_get('https://federatio.com/x', allowed_hosts=ALLOWED, max_bytes=15)

    @patch('ilovevoley.core.security.socket.getaddrinfo', return_value=_addrinfo('10.0.0.5'))
    @patch('ilovevoley.core.security.requests.Session')
    def test_does_not_request_when_ip_is_private(self, mock_session_cls, _):
        with self.assertRaises(UnsafeURL):
            safe_get('https://federatio.com/x', allowed_hosts=ALLOWED)

        mock_session_cls.assert_not_called()
