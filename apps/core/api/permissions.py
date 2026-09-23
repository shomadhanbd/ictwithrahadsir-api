"""Who may reach which part of the admin API.

Four roles (`apps.identity.models.User.Role`) map onto three tiers of access.
The tiers are the useful unit: an endpoint declares the tier it needs, not
the list of roles it tolerates.

    full admin      admin, or a Django superuser
                    -> accounts, money, pricing, who teaches what
    content staff   admin + moderator
                    -> notices, banners, testimonials, pages, the shop
                       catalogue, the contact inbox
    teaching staff  admin + teacher
                    -> courses, sections, lessons, exams, enrolment

Admin and teacher used to be the only distinction, and it was drawn once,
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
there. That is not hypothetical: it is how a teacher could once delete an
admin account. See `apps.identity.api.permissions`.
"""

from django.contrib.auth import get_user_model

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission


def _has_role(user, *roles) -> bool:
    """Whether `user` is signed in and holds one of `roles`.

    `is_superuser` short-circuits every check: a superuser can already edit any
    row through the admin site, so refusing them here would protect nothing and
    only confuse whoever is holding that account.

    Deliberately **not** `is_staff`. That used to be an independent flag set
    only by `create_superuser`, so short-circuiting on it meant the same thing.
    It is now derived -- `is_superuser or role in {admin, moderator}` -- and
    reading it here would hand every moderator a pass through `is_full_admin`
    and `is_teaching_staff`, i.e. payments, pricing, accounts and the teacher roster.
    """
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_superuser or user.role in roles)


def is_full_admin(user) -> bool:
    """Accounts, payments, pricing, roster -- anything destructive."""
    return _has_role(user, get_user_model().Role.ADMIN)


def is_content_staff(user) -> bool:
    """The published site: notices, banners, pages, shop, contact inbox."""
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.MODERATOR)


def is_teaching_staff(user) -> bool:
    """Courses and everything under them: sections, lessons, exams."""
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.TEACHER)


def is_admin_panel_user(user) -> bool:
    """Any of the three -- i.e. "may sign in to the admin panel at all"."""
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.TEACHER, role.MODERATOR)


class IsAdminRole(BasePermission):
    """May sign in to the admin panel. **Base class -- prefer a named tier.**

    Kept as the gate for the panel itself and as the shared base below. An
    endpoint that uses this directly is saying "any of admin, teacher or
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


class IsFullAdminOrTeacherReadOnly(IsAdminRole):
    """Admins manage the academic taxonomy; teachers may only read it.

    A teacher building an exam has to name a subject for a section and filter
    the question bank by chapter and topic. With the taxonomy admin-only, every
    one of those controls came back empty and the feature was unusable by the
    role it exists for -- measured, all six lookups returned 403.

    Writes stay with admins: which class levels and subjects exist decides what
    a teacher *is* and which class a student is in, which is a roster decision.
    """

    message = "Only an admin may change the academic taxonomy."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return is_teaching_staff(request.user)
        return is_full_admin(request.user)


class IsCourseTeacher(IsTeachingStaff):
    """Teaching staff, narrowed to the courses this teacher actually teaches.

    An admin passes everything. A teacher passes only for a course they hold
    a `courses.CourseTeacher` row against.

    Reached through `user.teaching` (the reverse accessor) rather
    than by importing `courses.CourseTeacher`: a permission in `core` that
    imported `courses` would drag the dependency the wrong way for the sake of
    one `.exists()`.

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
        return request.user.teaching.filter(course_id=course_id).exists()


def assert_may_manage_course(request, course_id) -> None:
    """`IsCourseTeacher`'s check, for views that fetch their own object.

    Several admin endpoints are plain `APIView`s that look a row up by hand
    -- the lesson toggle, the enrolment actions. DRF only runs
    `has_object_permission` from `generics.get_object()`, so those never
    reach it and would stay unscoped. Call this straight after fetching.
    """
    if is_full_admin(request.user):
        return
    if course_id is None or not request.user.teaching.filter(course_id=course_id).exists():
        raise PermissionDenied("This course is not yours to manage.")
