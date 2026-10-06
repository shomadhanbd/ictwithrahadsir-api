from rest_framework.permissions import SAFE_METHODS

from apps.core.api.permissions import SUPERUSER_ACCOUNT_MESSAGE, IsTeachingStaff, may_change_account
from apps.identity.roles import TEACHER_CREATABLE_ROLES, is_full_admin


class CanManageUsers(IsTeachingStaff):
    """Admins manage every account; a teacher may read their own students and add new student accounts."""

    message = "Only an admin may manage this account."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if is_full_admin(request.user) or request.method in SAFE_METHODS:
            return True
        if request.method != "POST":
            return False
        role = request.data.get("role")
        return (role is None or role in TEACHER_CREATABLE_ROLES) and "is_active" not in request.data

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if not may_change_account(request.user, obj):
            self.message = SUPERUSER_ACCOUNT_MESSAGE
            return False
        return is_full_admin(request.user)
