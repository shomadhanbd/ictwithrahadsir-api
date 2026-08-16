from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminRole(BasePermission):
    """Gates every `/admin/*` endpoint. Mirrors the admin panel's own model:
    any authenticated user with role in {admin, instructor} may manage
    content; only `admin` may manage users/payments (checked per-view where
    the existing admin UI actually restricts it -- in practice the current
    admin panel does not enforce this distinction either, see codebase
    reverse-engineering notes)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or user.role in ("admin", "instructor")))


class IsOwnerOrAdmin(BasePermission):
    """Object-level check for student-facing resources (cart, orders, ...)."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        owner = getattr(obj, "user", None) or getattr(obj, "user_id", None)
        if user.is_staff or getattr(user, "role", None) == "admin":
            return True
        return owner == user or owner == user.id


class ReadOnlyOrAdmin(BasePermission):
    """Public GET, admin-only writes -- used by public catalog endpoints
    that are also exposed for convenience under the same viewset."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and (user.is_staff or getattr(user, "role", None) in ("admin", "instructor")))
