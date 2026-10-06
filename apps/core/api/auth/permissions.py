"""Permission tiers: full admin, content staff (admin + moderator), teaching staff (admin + teacher)."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.identity.roles import is_content_staff, is_full_admin, is_teaching_staff

SUPERUSER_ACCOUNT_MESSAGE = "Only a superuser may change a superuser's account."


def may_change_account(actor, account) -> bool:
    """A superuser's account is changed only by a superuser: anyone else could set its phone, then reset its
    password by OTP. Every path that writes an account (user API, teachers API, Django admin) asks this."""
    return account is None or not account.is_superuser or bool(getattr(actor, "is_superuser", False))


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
    """Teaching staff build the curriculum; only an admin may delete part of it."""

    def has_permission(self, request, view):
        if request.method == "DELETE":
            self.message = "Only an admin may delete part of the curriculum."
            return is_full_admin(request.user)
        self.message = IsTeachingStaff.message
        return is_teaching_staff(request.user)


class IsFullAdminOrTeacherReadOnly(BasePermission):
    """Teaching staff read; only an admin writes."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            self.message = IsTeachingStaff.message
            return is_teaching_staff(request.user)
        self.message = "Only an admin may change this."
        return is_full_admin(request.user)
