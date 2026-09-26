"""Validaciones de seguridad para peticiones HTTP salientes (mitigación SSRF)."""

import ipaddress
import socket
from urllib.parse import urlparse

import requests

DEFAULT_TIMEOUT = 10
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024


class UnsafeURL(Exception):
    """La URL de destino no supera las validaciones anti-SSRF."""


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


def validate_url(url, allowed_hosts):
    """Valida esquema https, host en lista blanca y que resuelva a IPs públicas."""
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
    for ip in _resolve_ips(host, port):
        try:
            address = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise UnsafeURL(f'dirección IP no válida: {ip}') from exc
        if not address.is_global:
            raise UnsafeURL(f'la URL resuelve a una IP no pública: {ip}')
    return parsed


def safe_get(url, *, allowed_hosts, timeout=DEFAULT_TIMEOUT, max_bytes=DEFAULT_MAX_BYTES, headers=None):
    """GET validado contra SSRF: host en lista blanca, sin redirects y con límite de bytes."""
    validate_url(url, allowed_hosts)
    response = requests.get(
        url, timeout=timeout, allow_redirects=False, stream=True, headers=headers,
    )
    try:
        if response.is_redirect:
            raise UnsafeURL('la URL redirige a otro destino')
        response.raise_for_status()
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
    finally:
        response.close()
