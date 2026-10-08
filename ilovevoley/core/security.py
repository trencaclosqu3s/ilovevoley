"""Validaciones de seguridad para peticiones HTTP salientes (mitigación SSRF)."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import requests
import urllib3
from django.conf import settings
from requests.adapters import DEFAULT_POOLBLOCK, HTTPAdapter
from urllib3 import PoolManager
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024


class UnsafeURL(Exception):
    """La URL de destino no supera las validaciones anti-SSRF."""


class _PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
    """Conecta al IP validado conservando el hostname para Host y SNI.

    Evita el bypass por DNS rebinding: la conexión TCP va al IP ya comprobado,
    no a una segunda resolución del hostname.
    """

    def __init__(self, *args, pinned_ip=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip

    def _new_conn(self):
        if not self._pinned_ip:
            return super()._new_conn()
        original = self._dns_host
        self._dns_host = self._pinned_ip
        try:
            return super()._new_conn()
        finally:
            self._dns_host = original


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _PinnedHTTPSConnection


class _PinnedPoolManager(PoolManager):
    """PoolManager que inyecta el IP fijado en cada pool HTTPS."""

    def __init__(self, *args, pinned_ip=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pinned_ip = pinned_ip
        self.pool_classes_by_scheme = {
            'http': HTTPConnectionPool,
            'https': _PinnedHTTPSConnectionPool,
        }

    def _new_pool(self, scheme, host, port, request_context=None):
        if request_context is None:
            request_context = self.connection_pool_kw.copy()
        request_context['pinned_ip'] = self._pinned_ip
        return super()._new_pool(scheme, host, port, request_context=request_context)


class _PinnedIPAdapter(HTTPAdapter):
    """Adaptador de requests que fija las conexiones HTTPS a un IP concreto."""

    def __init__(self, pinned_ip, **kwargs):
        self._pinned_ip = pinned_ip
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=DEFAULT_POOLBLOCK, **pool_kwargs):
        self.poolmanager = _PinnedPoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            pinned_ip=self._pinned_ip,
            **pool_kwargs,
        )


def _host_is_allowed(host, allowed_hosts):
    host = (host or '').lower().rstrip('.')
    if not host:
        return False
    for allowed in allowed_hosts:
        allowed = (allowed or '').strip().lower().rstrip('.')
        if allowed and (host == allowed or host.endswith('.' + allowed)):
            return True
    return False


def _resolve_ips(host, port):
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise requests.exceptions.ConnectionError(str(exc)) from exc
    return {info[4][0] for info in infos}


def _is_public_ip(ip):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    mapped = getattr(address, 'ipv4_mapped', None)
    if mapped is not None and not mapped.is_global:
        return False
    return address.is_global


def validate_url(url, allowed_hosts):
    """Valida esquema https, host en lista blanca y que resuelva a IPs públicas.

    Devuelve ``(url_parseada, ip)`` con la IP pública a la que fijar la conexión.
    """
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise UnsafeURL('solo se permite el esquema https')
    host = parsed.hostname
    if not host:
        raise UnsafeURL('la URL no tiene host')
    if not _host_is_allowed(host, allowed_hosts):
        raise UnsafeURL(f'host no permitido: {host}')
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise UnsafeURL('puerto inválido') from exc

    ips = _resolve_ips(host, port)
    if not ips:
        raise requests.exceptions.ConnectionError(f'no se pudo resolver {host}')
    for ip in ips:
        if not _is_public_ip(ip):
            raise UnsafeURL(f'la URL resuelve a una IP no pública: {ip}')
    return parsed, sorted(ips)[0]


def _read_limited(response, max_bytes):
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise UnsafeURL('el contenido supera el tamaño máximo permitido')
        chunks.append(chunk)
    return b''.join(chunks)


def safe_get(url, *, allowed_hosts, timeout=DEFAULT_TIMEOUT, max_bytes=DEFAULT_MAX_BYTES, headers=None):
    """GET validado contra SSRF: host en lista blanca, sin redirects, límite de bytes
    y conexión fijada al IP ya resuelto y validado.
    """
    _, pinned_ip = validate_url(url, allowed_hosts)
    session = requests.Session()
    session.trust_env = False
    session.mount('https://', _PinnedIPAdapter(pinned_ip))
    try:
        response = session.get(
            url, timeout=timeout, allow_redirects=False, stream=True, headers=headers,
        )
        try:
            if response.is_redirect:
                raise UnsafeURL('la URL redirige a otro destino')
            response.raise_for_status()
            return _read_limited(response, max_bytes)
        finally:
            response.close()
    finally:
        session.close()


def fetch_logo_bytes(url: str | None, *, timeout: float = 5) -> bytes | None:
    """Descarga bytes de un escudo vía ``safe_get`` (hosts de ``ACTA_ALLOWED_HOSTS``)."""
    if not url:
        return None
    # La RFEVB guarda sus escudos con http:// y redirige a https; safe_get solo admite https.
    if url.startswith('http://'):
        url = 'https://' + url[len('http://'):]
    try:
        return safe_get(
            url,
            allowed_hosts=settings.ACTA_ALLOWED_HOSTS,
            timeout=timeout,
            max_bytes=2 * 1024 * 1024,
        )
    except Exception as exc:
        logger.warning('No se pudo descargar logo %s: %s', url, exc)
        return None
