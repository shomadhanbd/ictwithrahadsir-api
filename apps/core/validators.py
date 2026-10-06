from django.core.exceptions import ValidationError

from apps.core.net import is_fetchable_url


def validate_fetchable_url(value):
    if value and not is_fetchable_url(value):
        raise ValidationError("This link points to a private or unreachable address.")
