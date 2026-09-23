"""Who may reach which part of the private (admin) API.

Roles map onto three tiers, and each endpoint names the tier it needs:

    full admin      admin              accounts, money, pricing, who teaches what
    content staff   admin + moderator  notices, banners, testimonials, pages
    teaching staff  admin + teacher    courses, sections, lessons, exams, enrolment

A superuser passes every tier. Keep these checks in permission classes, not
serializers: a serializer never runs on DELETE.
"""

from django.contrib.auth import get_user_model

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission


def _has_role(user, *roles) -> bool:
    # Not `is_staff`: that flag is also true for moderators, and would let
    # them through the full-admin and teaching tiers.
    if not (user and user.is_authenticated):
        return False
    return bool(user.is_superuser or user.role in roles)


def is_full_admin(user) -> bool:
    return _has_role(user, get_user_model().Role.ADMIN)


def is_content_staff(user) -> bool:
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.MODERATOR)


def is_teaching_staff(user) -> bool:
    role = get_user_model().Role
    return _has_role(user, role.ADMIN, role.TEACHER)


class IsFullAdmin(BasePermission):
    message = "Only an admin may perform this action."

    def has_permission(self, request, view):
        return is_full_admin(request.user)


class IsContentStaff(BasePermission):
    message = "Only an admin or moderator may manage site content."

    def has_permission(self, request, view):
        return is_content_staff(request.user)


class IsTeachingStaff(BasePermission):
    message = "Only an admin or teacher may manage course material."

    def has_permission(self, request, view):
        return is_teaching_staff(request.user)


class IsTeachingStaffAdminDeletes(BasePermission):
    """Teaching staff build the curriculum (class levels, subjects, chapters,
    topics) as they file questions; only an admin may delete a part of it."""

    message = "Only an admin may delete part of the curriculum."

    def has_permission(self, request, view):
        if request.method == "DELETE":
            return is_full_admin(request.user)
        return is_teaching_staff(request.user)


class IsFullAdminOrTeacherReadOnly(BasePermission):
    """Teachers may read these (groups, batches); only admins may change them."""

    message = "Only an admin may change this."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return is_teaching_staff(request.user)
        return is_full_admin(request.user)


class IsCourseTeacher(IsTeachingStaff):
    """Teaching staff, limited to the courses the teacher is assigned to.

    Only guards single objects; pair it with `CourseScopedAdminMixin`, which
    filters list endpoints the same way.
    """

    message = "This course is not yours to manage."

    def has_object_permission(self, request, view, obj):
        return may_manage_course(request.user, view.course_id_for(obj))


def may_manage_course(user, course_id) -> bool:
    """An admin, or a teacher assigned to `course_id`. With no course to
    scope against, refuse rather than fall open."""
    if is_full_admin(user):
        return True
    return course_id is not None and user.teaching.filter(course_id=course_id).exists()


def assert_may_manage_course(request, course_id) -> None:
    """`IsCourseTeacher`'s check for plain `APIView`s that fetch their own
    object, where DRF never calls `has_object_permission`."""
    if not may_manage_course(request.user, course_id):
        raise PermissionDenied(IsCourseTeacher.message)
