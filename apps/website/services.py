import logging

from django.conf import settings

import requests

from apps.core.ordering import move, next_order
from apps.website.models import Banner, Section
from apps.website.registry import REGISTRY
from apps.website.validators import clean_section_content

logger = logging.getLogger(__name__)


def update_section(key: str, *, content=None, is_visible=None) -> Section:
    """Saves a section's content (checked against its fields) and/or whether it is shown."""
    spec = REGISTRY[key]
    section = Section.objects.filter(key=key).first() or Section(key=key, content=dict(spec.defaults))
    if content is not None:
        section.content = clean_section_content(key, content)
    if is_visible is not None and spec.can_hide:
        section.is_visible = is_visible
    section.save()
    return section


def reset_section(key: str) -> None:
    """Back to the registry's original copy."""
    Section.objects.filter(key=key).delete()


def next_banner_order() -> int:
    return next_order(Banner.objects.all())


def move_banner(banner: Banner, *, direction) -> None:
    move(banner, Banner.objects.all(), direction=direction)


def refresh_website() -> None:
    """Asks the student website to drop its cached copy; without a shared secret it refreshes within five minutes."""
    if not settings.WEBSITE_REVALIDATE_SECRET:
        return
    try:
        requests.post(
            f"{settings.FRONTEND_URL.rstrip('/')}/api/revalidate",
            headers={"X-Revalidate-Secret": settings.WEBSITE_REVALIDATE_SECRET},
            timeout=3,
        )
    except requests.RequestException as exc:
        logger.warning("Website revalidation failed: %s", exc)
