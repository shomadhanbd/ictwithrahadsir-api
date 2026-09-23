"""Bangladeshi mobile numbers, stored in the local `01XXXXXXXXX` form."""

from django.conf import settings
from django.core.exceptions import ValidationError

from phonenumber_field.phonenumber import to_python

BANGLADESH_CALLING_CODE = 880

INVALID_MESSAGE = "Enter a valid Bangladeshi phone number, e.g. 01810001111."


def normalize_phone(raw: str | None) -> str | None:
    """The canonical `01XXXXXXXXX` form, or `None` if not a BD mobile."""
    if not raw:
        return raw

    number = to_python(str(raw), region=settings.PHONENUMBER_DEFAULT_REGION)
    if number is None or number.country_code != BANGLADESH_CALLING_CODE or not number.is_valid():
        return None

    # Built by hand because `format_as(NATIONAL)` renders "01810-001111".
    return f"0{number.national_number}"


def validate_phone(value: str | None) -> None:
    """Field validator, so the admin reports a bad number as a field error."""
    if value and normalize_phone(value) is None:
        raise ValidationError(INVALID_MESSAGE, code="invalid_phone")
