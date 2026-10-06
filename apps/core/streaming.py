"""Streams a remote file through the API so its address stays private."""

import time
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.http import StreamingHttpResponse

import requests
from requests.adapters import HTTPAdapter
from rest_framework.exceptions import NotFound

from apps.core.net import is_fetchable_url, public_address

CHUNK_SIZE = 8192
TIMEOUT_SECONDS = 30  # to connect, and between two reads
TOTAL_SECONDS = 300  # for the whole download, so a slow drip cannot hold a worker
MAX_BYTES = 200 * 1024 * 1024
PASSED_HEADERS = ("Content-Length", "Content-Range", "Accept-Ranges")


class _PinnedAdapter(HTTPAdapter):
    """Connects to an address already checked, while TLS still checks the certificate against the real host."""

    def __init__(self, hostname):
        self._hostname = hostname
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs["server_hostname"] = self._hostname
        kwargs["assert_hostname"] = self._hostname
        super().init_poolmanager(*args, **kwargs)


def _open(url, *, headers):
    """GETs `url`, from the very address that was checked: a second DNS answer cannot point it inside the network."""
    options = {"stream": True, "timeout": TIMEOUT_SECONDS, "allow_redirects": False}
    if settings.STREAM_ALLOW_PRIVATE_HOSTS:
        return requests.get(url, headers=headers, **options)
    address = public_address(url)
    if address is None:
        return None
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    host = f"[{address}]" if ":" in address else address
    session = requests.Session()
    session.mount(f"{parts.scheme}://", _PinnedAdapter(parts.hostname))
    pinned = urlunsplit(parts._replace(netloc=f"{host}{port}"))
    return session.get(pinned, headers={**headers, "Host": f"{parts.hostname}{port}"}, **options)


def _capped(upstream):
    """The body, cut off once it runs past MAX_BYTES or TOTAL_SECONDS."""
    deadline = time.monotonic() + TOTAL_SECONDS
    sent = 0
    try:
        for chunk in upstream.iter_content(chunk_size=CHUNK_SIZE):
            sent += len(chunk)
            if sent > MAX_BYTES or time.monotonic() > deadline:
                return
            yield chunk
    finally:
        upstream.close()


def stream_file(
    url, *, filename, range_header=None, content_type="application/octet-stream", missing="File not found."
):
    """The file at `url` as an inline, uncached response of `content_type`; a `Range` request is passed on."""
    if not is_fetchable_url(url):
        raise NotFound(missing)
    try:
        upstream = _open(url, headers={"Range": range_header} if range_header else {})
    except requests.RequestException as exc:
        raise NotFound(missing) from exc
    if upstream is None:
        raise NotFound(missing)
    declared = upstream.headers.get("Content-Length", "")
    if upstream.status_code >= 300 or (declared.isdigit() and int(declared) > MAX_BYTES):
        upstream.close()
        raise NotFound(missing)
    response = StreamingHttpResponse(_capped(upstream), status=upstream.status_code, content_type=content_type)
    for header in PASSED_HEADERS:
        if header in upstream.headers:
            response[header] = upstream.headers[header]
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
