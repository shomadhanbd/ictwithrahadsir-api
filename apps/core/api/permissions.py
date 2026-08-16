from rest_framework.permissions import BasePermission


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
