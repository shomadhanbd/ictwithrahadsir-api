from django.conf import settings
from django.core.files.storage import default_storage


def public_link(name) -> str:
    """The URL browsers open a stored file at; never the request's host, which may be an internal one."""
    return settings.API_BASE_URL.rstrip("/") + default_storage.url(name)
