"""Who may reach which part of the admin API.

Four roles (`apps.identity.models.User.Role`) map onto three tiers of access.
The tiers are the useful unit: an endpoint declares the tier it needs, not
the list of roles it tolerates.

    full admin      admin, or a Django `is_staff` account
                    -> accounts, money, pricing, who teaches what
    content staff   admin + moderator
                    -> notices, banners, testimonials, pages, the shop
                       catalogue, the contact inbox
    teaching staff  admin + instructor
                    -> courses, sections, lessons, exams, enrolment

Admin and instructor used to be the only distinction, and it was drawn once,
for everything: `IsAdminRole` admitted both and every `/admin/*` endpoint used
it. So a teacher could open the payments screen, edit any account, and hand
out discount codes. There was no role at all for the person who posts notices.

Two rules keep this honest:

**Every admin endpoint names its tier.** Nothing should be left on bare
`IsAdminRole` -- that is the shared base the three tiers are built from, and
using it directly means "any of the three", which is almost never what an
endpoint means.

**Tiers are answered here, in permissions, not in serializers.** A serializer
is only built for create and update, so `destroy()` bypasses anything written
there. That is not hypothetical: it is how an instructor could once delete an
admin account. See `apps.identity.api.v1.permissions`.
"""

from django.contrib.auth import get_user_model

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def _has_role(user, *roles) -> bool:
    """Whether `user` is signed in and holds one of `roles`.

    `is_staff` short-circuits every check: a Django staff account can already
    edit any row through the admin site, so refusing them here would protect
    nothing and only confuse whoever is holding that account.
    """
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_staff or user.role in roles)


def is_full_admin(user) -> bool:
    """Accounts, payments, pricing, faculty -- anything destructive."""
    return _has_role(user, get_user_model().Role.ADMIN)


def is_content_staff(user) -> bool:
    """The published site: notices, banners, pages, shop, contact inbox."""
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.MODERATOR)


def is_teaching_staff(user) -> bool:
    """Courses and everything under them: sections, lessons, exams."""
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.INSTRUCTOR)


def is_admin_panel_user(user) -> bool:
    """Any of the three -- i.e. "may sign in to the admin panel at all"."""
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.INSTRUCTOR, role.MODERATOR)


class IsAdminRole(BasePermission):
    """May sign in to the admin panel. **Base class -- prefer a named tier.**

    Kept as the gate for the panel itself and as the shared base below. An
    endpoint that uses this directly is saying "any of admin, instructor or
    moderator", which is a real answer for almost nothing.
    """

    def has_permission(self, request, view):
        return is_admin_panel_user(request.user)


class IsFullAdmin(IsAdminRole):
    message = "Only an admin may perform this action."

    def has_permission(self, request, view):
        return is_full_admin(request.user)


class IsContentStaff(IsAdminRole):
    message = "Only an admin or moderator may manage site content."

    def has_permission(self, request, view):
        return is_content_staff(request.user)


class IsTeachingStaff(IsAdminRole):
    message = "Only an admin or teacher may manage course material."

    def has_permission(self, request, view):
        return is_teaching_staff(request.user)


class IsCourseInstructor(IsTeachingStaff):
    """Teaching staff, narrowed to the courses this teacher actually teaches.

    An admin passes everything. A teacher passes only for a course they hold
    a `faculty.CourseInstructor` row against -- which is what finally makes
    that row mean something: it has existed since the faculty rewrite and was
    never once consulted for access.

    Reached through `user.instructor_profiles` (the reverse accessor) rather
    than by importing `faculty.CourseInstructor`. `faculty` depends on
    `courses`, so a permission in `core` that imported it would drag the
    dependency the wrong way for the sake of one `.exists()`.

    Pair it with `apps.core.api.viewsets.CourseScopedAdminMixin`, which does
    the matching job for list endpoints. Object permissions only run on a
    single fetched row, so on their own they stop a teacher *opening* another
    course's lesson while still listing every one of them.
    """

    message = "This course is not yours to manage."

    def has_object_permission(self, request, view, obj):
        if is_full_admin(request.user):
            return True
        course_id = view.course_id_for(obj)
        if course_id is None:
            # Nothing to scope against -- refuse rather than fall open.
            return False
        return request.user.instructor_profiles.filter(course_id=course_id).exists()


def assert_may_manage_course(request, course_id) -> None:
    """`IsCourseInstructor`'s check, for views that fetch their own object.

    Several admin endpoints are plain `APIView`s that look a row up by hand
    -- the lesson toggle, the enrolment actions. DRF only runs
    `has_object_permission` from `generics.get_object()`, so those never
    reach it and would stay unscoped. Call this straight after fetching.
    """
    if is_full_admin(request.user):
        return
    if course_id is None or not request.user.instructor_profiles.filter(
        course_id=course_id
    ).exists():
        raise PermissionDenied("This course is not yours to manage.")
