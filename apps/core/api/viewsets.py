from rest_framework import viewsets

from .permissions import IsAdminRole


class SlugOrPkLookupMixin:
    """Resolve a detail route by pk when the URL segment is all digits.

    These viewsets look records up by slug so public URLs stay readable, but
    the admin panel routes on the numeric id -- it has that from the list
    response and never carries the slug around. Accepting both lets one
    endpoint serve the panel and the site.

    A slug that is itself all digits (a course titled "2026") would otherwise
    become unreachable, so a failed pk lookup falls through to the slug rather
    than 404ing.
    """

    def get_object(self):
        value = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        if value is not None and str(value).isdigit():
            queryset = self.filter_queryset(self.get_queryset())
            obj = queryset.filter(pk=value).first()
            if obj is not None:
                self.check_object_permissions(self.request, obj)
                return obj
        return super().get_object()


class AdminModelViewSet(viewsets.ModelViewSet):
    """Base for every `/admin/<resource>` CRUD endpoint: staff/admin-only.
    Uses the global Laravel-style paginator (clients can pass `per_page` up
    to 200 to effectively fetch "all" for dropdown/tree-style listings, the
    same way the existing admin panel already does against the real API)."""

    permission_classes = [IsAdminRole]
    lookup_field = "pk"
