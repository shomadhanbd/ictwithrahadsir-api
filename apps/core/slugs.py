"""ASCII slug generation for Bangla content.

Django's `slugify()` drops every non-ASCII character, so a Bangla title
slugifies to an empty string and every row falls back to a shared literal
("item", "item-2", ...) -- meaningless, order-dependent URLs.

`slugify(..., allow_unicode=True)` is not a usable alternative here:

  * it strips Bengali combining vowel marks, so "কোর্স" becomes "করস";
  * `SlugField` rejects non-ASCII unless every field also sets
    `allow_unicode=True` (a migration on every model); and
  * Django's `<slug:...>` path converter is `[-a-zA-Z0-9_]+`, so unicode
    slugs would 404 on every detail route in `urls.py`.

So we transliterate Bengali to ASCII first, then hand the result to
`slugify()` as usual. Output is stable, unique-able and route-safe.
"""

from django import forms
from django.core import validators as django_validators
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

# Independent vowels.
VOWELS = {
    "অ": "o",
    "আ": "a",
    "ই": "i",
    "ঈ": "i",
    "উ": "u",
    "ঊ": "u",
    "ঋ": "ri",
    "এ": "e",
    "ঐ": "oi",
    "ও": "o",
    "ঔ": "ou",
}

# Dependent vowel signs (matras), which replace a consonant's inherent "a".
MATRAS = {
    "া": "a",
    "ি": "i",
    "ী": "i",
    "ু": "u",
    "ূ": "u",
    "ৃ": "ri",
    "ে": "e",
    "ৈ": "oi",
    "ো": "o",
    "ৌ": "ou",
}

CONSONANTS = {
    "ক": "k",
    "খ": "kh",
    "গ": "g",
    "ঘ": "gh",
    "ঙ": "ng",
    "চ": "ch",
    "ছ": "chh",
    "জ": "j",
    "ঝ": "jh",
    "ঞ": "n",
    "ট": "t",
    "ঠ": "th",
    "ড": "d",
    "ঢ": "dh",
    "ণ": "n",
    "ত": "t",
    "থ": "th",
    "দ": "d",
    "ধ": "dh",
    "ন": "n",
    "প": "p",
    "ফ": "ph",
    "ব": "b",
    "ভ": "bh",
    "ম": "m",
    "য": "z",
    "র": "r",
    "ল": "l",
    "শ": "sh",
    "ষ": "sh",
    "স": "s",
    "হ": "h",
    "ড়": "r",
    "ঢ়": "rh",
    "য়": "y",
    "ৎ": "t",
}

# Marks that attach to a consonant without contributing a vowel.
SIGNS = {"ং": "ng", "ঃ": "h", "ঁ": "n"}

DIGITS = {
    "০": "0",
    "১": "1",
    "২": "2",
    "৩": "3",
    "৪": "4",
    "৫": "5",
    "৬": "6",
    "৭": "7",
    "৮": "8",
    "৯": "9",
}

HASANT = "্"  # virama: suppresses the inherent vowel, joining consonants


def transliterate(text):
    """Render Bengali script as ASCII. Characters outside the Bengali block
    (Latin, digits, punctuation) pass through untouched."""
    out = []
    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        if char in CONSONANTS:
            out.append(CONSONANTS[char])
            following = text[i + 1] if i + 1 < length else ""
            if following in MATRAS:
                out.append(MATRAS[following])
                i += 2
                continue
            if following == HASANT:
                # Conjunct: no inherent vowel before the next consonant.
                i += 2
                continue
            out.append("a")  # inherent vowel
            i += 1
            continue

        if char in VOWELS:
            out.append(VOWELS[char])
        elif char in DIGITS:
            out.append(DIGITS[char])
        elif char in SIGNS:
            out.append(SIGNS[char])
        elif char in MATRAS or char == HASANT:
            # Orphaned mark with no preceding consonant -- skip it.
            pass
        else:
            out.append(char)
        i += 1

    return "".join(out)


def ascii_slug(text, fallback="item"):
    """Slugify `text`, transliterating Bengali first so the result is never
    empty just because the source was non-Latin."""
    if not text:
        return fallback
    slug = slugify(text)
    if not slug:
        slug = slugify(transliterate(text))
    return slug[:200] or fallback


def unique_slug(instance, base_text, slug_field="slug", fallback="item"):
    """A slug for `instance` that no other row of its model holds.

    `courses` and `content` each had their own copy of this, with different
    signatures and the same behaviour: probe "title", then "title-2", then
    "title-3", one `EXISTS` query per attempt. That is fine for a unique
    title and quadratic for a common one -- seeding thirty "Model Test"
    contents cost 1 + 2 + ... + 30 queries.

    This reads the taken suffixes once and picks the first free number.

    `fallback` is the slug used when `base_text` transliterates to nothing --
    a product named only in punctuation, say. It exists because `store` kept
    its own copy of this function purely to pass "product" instead of "item".
    """
    base = ascii_slug(base_text, fallback=fallback)
    model = instance.__class__

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


#: Django's unicode slug validator is `^[-\w]+\Z`, and `\w` excludes the
#: combining vowel marks almost every Bangla word carries -- `বিজ্ঞান` is
#: rejected, `কম` is not. Widening it by the Bengali block is what makes a
#: typed Bangla slug possible at all.
BENGALI_BLOCK = "\u0980-\u09ff"

validate_bangla_slug = RegexValidator(
    rf"^[-\w{BENGALI_BLOCK}]+\Z",
    "Enter a valid slug consisting of letters, numbers, underscores or hyphens.",
    "invalid",
)

#: Whichever of these Django installed, it rejects Bangla.
STOCK_SLUG_VALIDATORS = (
    django_validators.validate_slug,
    django_validators.validate_unicode_slug,
)


def swap_slug_validator(field):
    """Put `validate_bangla_slug` in place of Django's, on a model or form field.

    Edited in place rather than via `default_validators`: `CharField.__init__`
    already reads `field.validators` to append a `MaxLengthValidator`, which
    materialises the `cached_property`, so assigning `default_validators`
    afterwards is never consulted.
    """
    field.validators[:] = [v for v in field.validators if v not in STOCK_SLUG_VALIDATORS] + [validate_bangla_slug]


class BanglaSlugFormField(forms.SlugField):
    """The form half -- a model field's validators never reach the form."""

    def __init__(self, **kwargs):
        kwargs.setdefault("allow_unicode", True)
        super().__init__(**kwargs)
        swap_slug_validator(self)


class BanglaSlugField(models.SlugField):
    """A `SlugField` that also accepts Bengali.

    Only widens what a human may type; `unique_slug` still generates ASCII.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_unicode", True)
        super().__init__(*args, **kwargs)
        swap_slug_validator(self)

    def formfield(self, **kwargs):
        return super().formfield(**{"form_class": BanglaSlugFormField, **kwargs})
