from rest_framework import viewsets
from rest_framework.response import Response

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


class UnpaginatedDataListMixin:
    """List endpoints that return `{"data": [...]}` with no pagination block.

    Several endpoints are deliberately unpaginated -- a course's materials, a
    category tree, the practice topics -- but the frontends still expect the
    payload under a `data` key, because that is where the paginated envelope
    puts it. Every such view previously set `pagination_class = None` and then
    overrode `list()` to add the key back by hand; this is those two lines,
    written once.

    Subclasses that need to build the page themselves (to attach a batched
    serializer context, say) should override `get_list_payload` rather than
    `list`.
    """

    pagination_class = None

    def get_list_payload(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.get_serializer(queryset, many=True).data

    def list(self, request, *args, **kwargs):
        return Response({'data': self.get_list_payload(request, *args, **kwargs)})


class SchemaSafeQuerysetMixin:
    """Keeps `get_queryset` from being run for real during schema generation.

    drf-spectacular introspects a view by calling `get_queryset()` with a
    fake request: no URL kwargs and an anonymous user. Any view whose
    queryset depends on `self.kwargs` or `request.user` raises there, and the
    generator then falls back to an untyped response.

    Views using this must also declare a `queryset` attribute (an empty one
    is fine) so the model can still be identified.
    """

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.model.objects.none()
        return super().get_queryset()
