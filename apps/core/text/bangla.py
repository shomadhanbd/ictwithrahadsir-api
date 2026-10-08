"""Text shown to students, who read the site in Bangla."""

_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def bn_digits(value) -> str:
    """`value` written with Bangla digits: 12 -> "১২"."""
    return str(value).translate(_DIGITS)
