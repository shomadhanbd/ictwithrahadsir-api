"""Every editable part of the student website: its fields and the copy it shows until an admin edits it.

A section's page decides which admin tab lists it; the order here is the order the admin shows them in.
"""

from apps.website.registry import about, home, legal, pages, site
from apps.website.registry.fields import SectionSpec

PAGES = (
    ("global", "Whole site"),
    ("home", "Home"),
    ("about", "About (পরিচিতি)"),
    ("courses", "Courses page"),
    ("materials", "Study material page"),
    ("notice", "Notice page"),
    ("auth", "Sign-in"),
    ("legal", "Policy pages"),
)

LEGAL_PREFIX = legal.PREFIX

SECTIONS: tuple[SectionSpec, ...] = (*site.SECTIONS, *home.SECTIONS, *about.SECTIONS, *pages.SECTIONS, *legal.SECTIONS)

REGISTRY: dict[str, SectionSpec] = {spec.key: spec for spec in SECTIONS}


def get_spec(key: str) -> SectionSpec | None:
    return REGISTRY.get(key)


def legal_key(slug: str) -> str:
    return f"{LEGAL_PREFIX}{slug}"
