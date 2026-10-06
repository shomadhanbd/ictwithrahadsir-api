"""Texts sent to enrolled students; English only, since course titles are often Bangla."""

from django.conf import settings
from django.utils import timezone


def expiry_reminder(enrollment) -> str:
    ends = timezone.localtime(enrollment.valid_till).strftime("%d %b %Y")
    renew = f"{settings.FRONTEND_URL.rstrip('/')}/course/{enrollment.course.slug}"
    return f"Your course access ends on {ends}. Renew here: {renew}"
