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

from django.utils.text import slugify

# Independent vowels.
VOWELS = {
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u",
    "ঋ": "ri", "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
}

# Dependent vowel signs (matras), which replace a consonant's inherent "a".
MATRAS = {
    "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri",
    "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou",
}

CONSONANTS = {
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng",
    "চ": "ch", "ছ": "chh", "জ": "j", "ঝ": "jh", "ঞ": "n",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "ph", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "z", "র": "r", "ল": "l",
    "শ": "sh", "ষ": "sh", "স": "s", "হ": "h",
    "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t",
}

# Marks that attach to a consonant without contributing a vowel.
SIGNS = {"ং": "ng", "ঃ": "h", "ঁ": "n"}

DIGITS = {
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
    "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
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
