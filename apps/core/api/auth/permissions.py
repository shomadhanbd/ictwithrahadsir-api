"""Permission tiers: full admin, content staff (admin + moderator), teaching staff (admin + teacher)."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.identity.roles import is_content_staff, is_full_admin, is_staff_member, is_teaching_staff


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


class IsStaffMember(BasePermission):
    message = "Only back-office staff may do this."

    def has_permission(self, request, view):
        return is_staff_member(request.user)


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


class StaffMayReadMixin:
    """Every staff member reads, so moderators' forms can offer these as choices; writes keep the view's rules."""

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsStaffMember()]
        return super().get_permissions()
