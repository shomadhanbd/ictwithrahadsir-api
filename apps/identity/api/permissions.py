from rest_framework.permissions import SAFE_METHODS

from apps.core.api.auth.permissions import IsTeachingStaff
from apps.identity.roles import (
    SUPERUSER_ACCOUNT_MESSAGE,
    TEACHER_CREATABLE_ROLES,
    is_full_admin,
    may_change_account,
)


class CanManageUsers(IsTeachingStaff):
    """Admins manage every account. A teacher may read their own students and create student accounts."""

    message = "Only an admin may manage this account."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if is_full_admin(request.user):
            return True

        # A teacher: reads are scoped to their own students by the view's queryset.
        if request.method in SAFE_METHODS:
            return True
        if request.method != "POST":
            return False
        role = request.data.get("role")
        creates_a_student = role is None or role in TEACHER_CREATABLE_ROLES
        return creates_a_student and "is_active" not in request.data

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if not may_change_account(request.user, obj):
            self.message = SUPERUSER_ACCOUNT_MESSAGE
            return False
        return is_full_admin(request.user)
