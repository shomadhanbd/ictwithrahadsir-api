"""Reads for the CMS payloads, chiefly the homepage aggregate.

The homepage is one round trip that gathers seven things from four apps.
Doing that in the view meant importing `courses` *inside* the handler to dodge
an import cycle -- `content` is imported by that app, so a module-scope import
back into it would close the loop.

Gathering it here removes the reason for the cycle rather than hiding it: the
selector is imported lazily by the one view that needs it, so nothing is
imported at module-scope in either direction.
"""

from apps.content.models import Advertisement, Page, Testimonial

# `profiles` sits below `content` and imports nothing from it, so the roster
# needs none of the lazy-import dance that `courses` does.
from apps.profiles.models import TeacherProfile

#: The homepage shows featured courses only, and never the whole catalogue.
FEATURED_COURSE_LIMIT = 12

#: The most teachers `/home` returns; the About page lists them all, so it is generous.
HOME_INSTRUCTORS = 50

#: The `Page` key holding the homepage banner image.
BANNER_PAGE_KEY = 'homeBannerImage'

#: The counter whose value is rendered as the success-story figure.
SUCCESS_STORY_COUNTER_KEY = 'homeInstructorCounter'


def homepage_content(user=None):
    """Everything the landing page needs, as model instances.

    Returns a dict of querysets/lists rather than serialised data: rendering
    is the serializer's job, and keeping this layer free of `request` means
    it can be called from a warm-cache job later without faking one. `user`
    narrows the featured courses to the ones they may see; none means a
    visitor, who sees them all.
    """
    from apps.courses.models import Course

    courses = list(
        Course.objects.published().featured().visible_to(user).with_catalogue_prefetch()[:FEATURED_COURSE_LIMIT]
    )

    # Homepage counters and banner are managed as `Page` rows through the
    # admin panel's Pages screen (value_type="counter"/"image"), not the
    # separate `Counter` model, which nothing in either frontend edits.
    # Listed once and reused: `counters` is iterated for both the counter
    # payload and the success-story lookup.
    counters = list(Page.objects.filter(value_type=Page.ValueType.COUNTER))

    return {
        'courses': courses,
        'counters': counters,
        'banner': Page.objects.filter(key=BANNER_PAGE_KEY).first(),
        'success_story': next((c.value for c in counters if c.key == SUCCESS_STORY_COUNTER_KEY), 0),
        'advertisements': Advertisement.objects.all(),
        'testimonials': Testimonial.objects.all(),
        # Active accounts only; the About page reuses this as the whole roster, so the cap only bounds the payload.
        'instructors': TeacherProfile.objects.filter(user__is_active=True).select_related('user')[:HOME_INSTRUCTORS],
    }
