import hashlib

from rest_framework import serializers

from apps.core.phones import INVALID_MESSAGE, normalize_phone


class MediaField(serializers.Field):
    """A file referenced by its absolute URL.

    Reads as `{id, link}` (or the bare URL with `bare=True`); writes take the
    URL string.
    """

    def __init__(self, *, bare=False, **kwargs):
        self.bare = bare
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)
        # Without this the OpenAPI schema types the field as a plain string.
        self._spectacular_annotation = {
            "field": {"type": "string", "format": "uri", "nullable": True}
            if self.bare
            else {
                "type": "object",
                "nullable": True,
                "properties": {
                    "id": {"type": "integer"},
                    "link": {"type": "string", "format": "uri"},
                },
                "required": ["id", "link"],
            }
        }

    def to_representation(self, value):
        if not value:
            return None
        if self.bare:
            return value
        digest = hashlib.md5(value.encode()).hexdigest()[:8]
        return {"id": int(digest, 16) % 1_000_000, "link": value}

    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip():
            return data.strip()
        raise serializers.ValidationError("Expected a URL string.")


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
