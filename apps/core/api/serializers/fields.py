from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator

from rest_framework import serializers

from apps.core.text.html import clean_html
from apps.core.text.phones import INVALID_MESSAGE, normalize_phone


class MediaField(serializers.Field):
    """A file link: written as a URL string, read as `{"link": url}` (or the bare URL with `bare=True`).

    `max_length` matches the model's URLField; declaring a field by hand skips the check DRF would add.
    `null_as` is what "no file" is stored as: `""` for a column that does not allow null.
    """

    def __init__(self, *, bare=False, max_length=200, null_as=None, **kwargs):
        self.bare = bare
        self.max_length = max_length
        self.null_as = null_as
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def to_representation(self, value):
        if not value:
            return None
        return value if self.bare else {"link": value}

    def validate_empty_values(self, data):
        is_empty, value = super().validate_empty_values(data)
        if is_empty and data is None:
            return True, self.null_as
        return is_empty, value

    def to_internal_value(self, data):
        url = data.strip() if isinstance(data, str) else ""
        if not url:
            raise serializers.ValidationError("Expected a URL string.")
        try:
            URLValidator(schemes=["http", "https"])(url)
        except DjangoValidationError as exc:
            raise serializers.ValidationError("Enter a full link starting with http:// or https://.") from exc
        if len(url) > self.max_length:
            raise serializers.ValidationError(f"Use a link of at most {self.max_length} characters.")
        return url


class PhoneField(serializers.CharField):
    """Accepts any spelling of a BD mobile number and stores `01XXXXXXXXX`."""

    default_error_messages = {"invalid_phone": INVALID_MESSAGE}

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        if not raw:  # blank, when the field allows it
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
    """A read-only annotated count; 0 on a row just created (no annotation yet)."""

    def __init__(self, **kwargs):
        super().__init__(read_only=True, default=0, **kwargs)
