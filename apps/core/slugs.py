"""Unique English slugs; a title with no English letters falls back to the model name."""

from django.utils.text import slugify


def unique_slug(instance, base_text, slug_field="slug"):
    """A slug no other row of the model holds, found with a single query."""
    model = instance.__class__
    limit = model._meta.get_field(slug_field).max_length - 6  # room for "-<n>"
    base = slugify(base_text)[:limit].strip("-") or model._meta.model_name
    if base.isdigit():
        # Detail routes read an all-digit segment as a pk, so "2027" would open whichever row has pk 2027.
        base = f"{model._meta.model_name}-{base}"

    taken = set(
        model.objects.filter(**{f"{slug_field}__startswith": base})
        .exclude(pk=instance.pk)
        .values_list(slug_field, flat=True)
    )
    if base not in taken:
        return base

    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"
