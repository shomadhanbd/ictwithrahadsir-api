import hashlib

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator

from rest_framework import serializers

from apps.core.html import clean_html
from apps.core.phones import INVALID_MESSAGE, normalize_phone


class MediaField(serializers.Field):
    """A file URL; reads as `{id, link}` (or the bare URL with `bare=True`)."""

    def __init__(self, *, bare=False, **kwargs):
        self.bare = bare
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return None
        if self.bare:
            return value
        digest = hashlib.md5(value.encode()).hexdigest()[:8]
        return {"id": int(digest, 16) % 1_000_000, "link": value}

    def to_internal_value(self, data):
        if not isinstance(data, str) or not data.strip():
            raise serializers.ValidationError("Expected a URL string.")
        try:
            URLValidator(schemes=["http", "https"])(data.strip())
        except DjangoValidationError as exc:
            raise serializers.ValidationError("Enter a full link starting with http:// or https://.") from exc
        return data.strip()


class PhoneField(serializers.CharField):
    """Accepts any spelling of a BD mobile number and stores `01XXXXXXXXX`."""

    default_error_messages = {"invalid_phone": INVALID_MESSAGE}

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        if not raw:  # only reachable with allow_blank=True
            return raw
        phone = normalize_phone(raw)
        if not phone:
            self.fail("invalid_phone")
        return phone


class EmailField(serializers.EmailField):
    """Lowercases the address."""

    def to_internal_value(self, data):
        return super().to_internal_value(data).lower()


class HtmlField(serializers.CharField):
    """Rich text from an editor; stored only after anything that can run script is stripped."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        return clean_html(super().to_internal_value(data))


class LiveCount(serializers.IntegerField):
    """A read-only annotated count; 0 on a freshly created row."""

    def __init__(self, **kwargs):
        super().__init__(read_only=True, default=0, **kwargs)
