from rest_framework import viewsets

from .permissions import IsAdminRole


class AdminModelViewSet(viewsets.ModelViewSet):
    """Base for every `/admin/<resource>` CRUD endpoint: staff/admin-only.
    Uses the global Laravel-style paginator (clients can pass `per_page` up
    to 200 to effectively fetch "all" for dropdown/tree-style listings, the
    same way the existing admin panel already does against the real API)."""

    permission_classes = [IsAdminRole]
    lookup_field = "pk"
