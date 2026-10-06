"""Bangla digits and dates for text sent to students."""

from django.utils import timezone

_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_MONTHS = [
    "জানুয়ারি",
    "ফেব্রুয়ারি",
    "মার্চ",
    "এপ্রিল",
    "মে",
    "জুন",
    "জুলাই",
    "আগস্ট",
    "সেপ্টেম্বর",
    "অক্টোবর",
    "নভেম্বর",
    "ডিসেম্বর",
]


def bn_digits(value) -> str:
    return str(value).translate(_DIGITS)


def bn_date(moment) -> str:
    """`12 অক্টোবর 2026` in Bangla digits, in local time."""
    local = timezone.localtime(moment)
    return bn_digits(f"{local.day} {_MONTHS[local.month - 1]} {local.year}")
