from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from apps.courses.models import Course, Enrollment
from apps.feedback.selectors import featured_feedback
from apps.profiles.models import TeacherProfile
from apps.website.models import Banner, Section
from apps.website.registry import LEGAL_PREFIX, REGISTRY, SECTIONS, SectionSpec

#: The home page shows featured courses only, and never the whole catalogue.
FEATURED_COURSE_LIMIT = 12
#: The About page lists every teacher from this too, so it is generous.
HOME_INSTRUCTORS = 50

STAT_COUNTERS = {
    "courses": lambda: Course.objects.published().count(),
    "students": lambda: Enrollment.objects.values("user").distinct().count(),
    "teachers": lambda: TeacherProfile.objects.filter(user__is_active=True).count(),
}


@dataclass(frozen=True)
class SectionState:
    """A registered section as it stands: the edited copy over the registry defaults."""

    spec: SectionSpec
    content: dict
    is_visible: bool = True
    updated_at: datetime | None = None

    @property
    def is_shown(self) -> bool:
        return self.is_visible or not self.spec.can_hide


def _state(spec: SectionSpec, row: Section | None) -> SectionState:
    stored = row.content if row else {}
    # Copied, so a caller cannot change the registry's defaults; fields added since the edit take their default.
    content = {name: deepcopy(stored.get(name, default)) for name, default in spec.defaults.items()}
    if row is None:
        return SectionState(spec, content)
    return SectionState(spec, content, row.is_visible, row.updated_at)


def section_states() -> list[SectionState]:
    """Every registered section, in registry order."""
    rows = {row.key: row for row in Section.objects.all()}
    return [_state(spec, rows.get(spec.key)) for spec in SECTIONS]


def section_state(key: str) -> SectionState:
    return _state(REGISTRY[key], Section.objects.filter(key=key).first())


def site_payload() -> dict:
    """Every shown section but the policy pages, keyed by name; the one payload every website page shares."""
    return {
        state.spec.key: state.content
        for state in section_states()
        if state.is_shown and not state.spec.key.startswith(LEGAL_PREFIX)
    }


def active_banners():
    now = timezone.now()
    return Banner.objects.filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        is_active=True,
    )


def site_stats() -> list[dict]:
    """The home page numbers: each counted from the site unless the admin typed one; zeros are left out."""
    state = section_state("home.stats")
    if not state.is_shown:
        return []
    stats = []
    for item in state.content["items"]:
        counter = STAT_COUNTERS.get(item["metric"])
        value = item["value"] or (str(counter()) if counter else "")
        if value and value != "0":
            stats.append({"label": item["label"], "value": value})
    return stats


def home_content(user=None) -> dict:
    """Everything the home page shows besides its copy; `user` narrows the courses to the ones they may see."""
    courses = Course.objects.published().featured().visible_to(user).with_catalogue_prefetch()
    return {
        "courses": list(courses[:FEATURED_COURSE_LIMIT]),
        "banners": active_banners(),
        "testimonials": featured_feedback(),
        "stats": site_stats(),
        "instructors": TeacherProfile.objects.filter(user__is_active=True).select_related("user")[:HOME_INSTRUCTORS],
    }
