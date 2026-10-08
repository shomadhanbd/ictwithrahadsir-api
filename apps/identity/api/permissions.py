from rest_framework.permissions import SAFE_METHODS

from apps.core.api.auth.permissions import IsTeachingStaff
from apps.identity.roles import (
    SUPERUSER_ACCOUNT_MESSAGE,
    is_full_admin,
    may_change_account,
)


class CanManageUsers(IsTeachingStaff):
    """Admins manage every account; a teacher only reads their own students."""

    message = "Only an admin may manage this account."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if is_full_admin(request.user):
            return True

        # A teacher reads, scoped to their own students by the view's queryset; students sign up themselves.
        return request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if not may_change_account(request.user, obj):
            self.message = SUPERUSER_ACCOUNT_MESSAGE
            return False
        return is_full_admin(request.user)
