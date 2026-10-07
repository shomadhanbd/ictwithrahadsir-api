"""Texts sent to enrolled students; English only, since course titles are often Bangla."""

from django.conf import settings
from django.utils import timezone


def _renew_link(enrollment) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/course/{enrollment.course.slug}"


def expiry_reminder(enrollment) -> str:
    ends = timezone.localtime(enrollment.valid_till).strftime("%d %b %Y")
    return f"Your course access ends on {ends}. Renew here: {_renew_link(enrollment)}"


def access_ended(enrollment) -> str:
    ended = timezone.localtime(enrollment.valid_till).strftime("%d %b %Y")
    return f"Your course access ended on {ended}. Renew to continue: {_renew_link(enrollment)}"
