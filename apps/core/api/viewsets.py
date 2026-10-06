from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.api.permissions import IsFullAdmin


class AdminOnlyFieldsMixin:
    """Teaching staff edit the row; changing one of `admin_only_fields` (moving it under another parent,
    switching it off) restructures everything below it, so it is an admin's call."""

    admin_only_fields = ()
    admin_only_message = "Only an admin may change this."

    def perform_update(self, serializer):
        instance, data = serializer.instance, serializer.validated_data
        changed = [
            field for field in self.admin_only_fields if field in data and data[field] != getattr(instance, field)
        ]
        if changed and not IsFullAdmin().has_permission(self.request, self):
            raise PermissionDenied(self.admin_only_message)
        super().perform_update(serializer)


class SlugOrPkLookupMixin:
    """Looks a detail route up by pk when the segment is all digits, else by slug."""

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
    """Base for private CRUD endpoints; defaults to the strictest tier so a forgotten permission fails closed."""

    permission_classes = [IsFullAdmin]
    lookup_field = "pk"


class UnpaginatedDataListMixin:
    """An unpaginated list wrapped as `{"data": [...]}`; override `get_list_payload` to customise rows."""

    pagination_class = None

    def get_list_payload(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.get_serializer(queryset, many=True).data

    def list(self, request, *args, **kwargs):
        return Response({"data": self.get_list_payload(request, *args, **kwargs)})
