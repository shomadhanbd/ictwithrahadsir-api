from rest_framework import viewsets
from rest_framework.response import Response

from apps.core.api.permissions import IsCourseTeacher, IsFullAdmin, is_full_admin


class SlugOrPkLookupMixin:
    """Look a detail route up by pk when the segment is all digits, else by
    slug -- the admin panel routes by id, the public site by slug.

    A slug that is itself all digits still resolves: a failed pk lookup falls
    through to the slug.
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
    """Base for private CRUD endpoints.

    Subclasses set their own `permission_classes`. The default is the
    strictest tier, so a viewset that forgets fails closed.
    """

    permission_classes = [IsFullAdmin]
    lookup_field = "pk"


class UnpaginatedDataListMixin:
    """An unpaginated list still wrapped as `{"data": [...]}`.

    Override `get_list_payload`, not `list`, to customise the rows.
    """

    pagination_class = None

    def get_list_payload(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return self.get_serializer(queryset, many=True).data

    def list(self, request, *args, **kwargs):
        return Response({'data': self.get_list_payload(request, *args, **kwargs)})


class SchemaSafeQuerysetMixin:
    """Returns an empty queryset during OpenAPI generation, for views whose
    queryset needs URL kwargs or a real user. The view must still declare a
    `queryset` so the model can be identified."""

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset.model.objects.none()
        return super().get_queryset()


class CourseScopedAdminMixin:
    """Limits a course-owned resource to the courses a teacher teaches.

    `get_queryset` filters lists; `IsCourseTeacher` guards single objects.
    `course_field` is the column holding the owning course (`id` on `Course`).
    """

    permission_classes = [IsCourseTeacher]
    course_field = "course_id"

    def course_id_for(self, obj):
        return getattr(obj, self.course_field, None)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if getattr(self, 'swagger_fake_view', False) or not user.is_authenticated:
            return queryset.none()
        if is_full_admin(user):
            return queryset

        taught = user.teaching.values_list('course_id', flat=True)
        return queryset.filter(**{f'{self.course_field}__in': taught})
