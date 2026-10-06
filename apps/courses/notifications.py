"""Texts sent to enrolled students."""

from django.conf import settings

from apps.core.bangla import bn_date


def expiry_reminder(enrollment) -> str:
    return (
        f"{enrollment.course.title} কোর্সে আপনার এক্সেস {bn_date(enrollment.valid_till)} তারিখে শেষ হবে। "
        f"রিনিউ করুন: {settings.FRONTEND_URL.rstrip('/')}/course/{enrollment.course.slug}"
    )
