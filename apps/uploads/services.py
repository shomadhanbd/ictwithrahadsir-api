from uuid import uuid4

from django.core.files.storage import default_storage
from django.utils import timezone


def save_upload(file, *, kind, extension) -> str:
    """Stores an already-checked file under a fresh name; returns its storage name."""
    name = f"uploads/{kind}/{timezone.now():%Y/%m}/{uuid4().hex}.{extension}"
    return default_storage.save(name, file)
