from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator

from apps.core.text.html import clean_html
from apps.website.registry import get_spec

MAX_LENGTH = {"text": 300, "textarea": 3000}
_url = URLValidator(schemes=["http", "https"])
_email = EmailValidator()


def validate_link(value: str) -> None:
    """A page on this site (`/course`, `#faq`) or a full web, phone or email link."""
    if not value.startswith(("/", "#", "tel:", "mailto:")):
        _url(value)


def validate_image_link(value: str) -> None:
    """An uploaded image's full link, or a file the website itself serves (`/images/...`)."""
    if not value.startswith("/") or value.startswith("//"):
        _url(value)


def validate_banner_dates(*, starts_at, ends_at) -> None:
    if starts_at and ends_at and ends_at <= starts_at:
        raise ValidationError({"ends_at": "The end must be after the start."})


def _clean_text(field, value: str) -> str:
    """One non-list value, checked for its type; raises ValidationError."""
    if field.type in MAX_LENGTH and len(value) > MAX_LENGTH[field.type]:
        raise ValidationError("This text is too long.")
    if field.type == "image":
        validate_image_link(value)
    elif field.type == "link":
        validate_link(value)
    elif field.type == "email":
        _email(value)
    elif field.type in ("icon", "choice") and value not in {v for v, _ in field.choices}:
        raise ValidationError("Choose one of the options.")
    elif field.type == "html":
        return clean_html(value)
    return value


def _clean_value(field, value, path, errors):
    if field.type == "list":
        if not isinstance(value, list):
            errors[path] = ["Expected a list."]
            return []
        if field.max_items and len(value) > field.max_items:
            errors[path] = [f"At most {field.max_items} items."]
            return []
        return [_clean_fields(field.fields, item, f"{path}.{i}", errors) for i, item in enumerate(value)]

    if value is None:
        value = ""
    if not isinstance(value, str):
        errors[path] = ["Expected text."]
        return ""
    value = value.strip()
    if not value:
        if field.required:
            errors[path] = ["This field is required."]
        return ""
    try:
        return _clean_text(field, value)
    except ValidationError as exc:
        errors[path] = exc.messages
        return value


def _clean_fields(fields, data, prefix, errors):
    if not isinstance(data, dict):
        errors[prefix or "content"] = ["Expected an object."]
        return {}

    def path(name):
        return f"{prefix}.{name}" if prefix else name

    for name in sorted(set(data) - {field.name for field in fields}):
        errors[path(name)] = ["Unknown field."]
    return {
        field.name: _clean_value(field, data.get(field.name, field.default), path(field.name), errors)
        for field in fields
    }


def clean_section_content(key: str, content) -> dict:
    """The content checked against the section's fields; missing fields take their defaults.

    Errors are keyed by path, e.g. `points.1.text`."""
    spec = get_spec(key)
    if spec is None:
        raise ValidationError({"key": "Unknown section."})
    errors = {}
    cleaned = _clean_fields(spec.fields, content, "", errors)
    if errors:
        raise ValidationError(errors)
    return cleaned
