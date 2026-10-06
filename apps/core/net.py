"""Guards against making the server fetch addresses inside its own network."""

import ipaddress
import socket
from urllib.parse import urlsplit

from django.conf import settings


def _is_public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def public_address(url: str) -> str | None:
    """The address to connect to for `url`, if every address its host resolves to is public; else None."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        resolved = socket.getaddrinfo(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return None
    addresses = [info[4][0] for info in resolved]
    if not addresses or not all(_is_public_ip(address) for address in addresses):
        return None
    return addresses[0]


def is_fetchable_url(url: str) -> bool:
    """An http(s) URL whose host resolves only to public addresses (any host when private ones are allowed)."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    return settings.STREAM_ALLOW_PRIVATE_HOSTS or public_address(url) is not None
