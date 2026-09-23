from rest_framework.permissions import SAFE_METHODS

from apps.core.api.permissions import IsTeachingStaff, is_full_admin
from apps.identity.models import User

TEACHER_MANAGEABLE_ROLES = {User.Role.STUDENT}


class CanManageUsers(IsTeachingStaff):
    message = "Only an admin may manage this account."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True

        role = request.data.get("role")
        if role is not None and role not in TEACHER_MANAGEABLE_ROLES:
            return is_full_admin(request.user)
        if "is_active" in request.data:
            return is_full_admin(request.user)
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS or is_full_admin(request.user):
            return True
        if obj.role not in TEACHER_MANAGEABLE_ROLES:
            return False
        return request.method != "DELETE"
