"""Unique English slugs.

Slugs are English only. A blank one is built from the title with Django's
`slugify`; a title with no English letters (a Bangla one, say) slugifies to
nothing and falls back to the model name, so it becomes `course`, `course-2`,
... until an admin types a proper slug.
"""

from django.utils.text import slugify


def unique_slug(instance, base_text, slug_field="slug"):
    """A slug for `instance` that no other row of its model holds.

    Reads the taken suffixes once and picks the first free number, rather
    than probing "title", "title-2", "title-3" with one query each.
    """
    model = instance.__class__
    # Leave room for a "-<n>" suffix within the column.
    limit = model._meta.get_field(slug_field).max_length - 6
    base = slugify(base_text)[:limit].strip("-") or model._meta.model_name

    taken = set(
        model.objects.filter(**{f"{slug_field}__startswith": base})
        .exclude(pk=instance.pk)
        .values_list(slug_field, flat=True)
    )
    if base not in taken:
        return base

    # `startswith` also matches unrelated longer slugs ("math" vs
    # "mathematics"), which is harmless: they simply never collide with a
    # candidate, so the first free suffix is still correct.
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"
