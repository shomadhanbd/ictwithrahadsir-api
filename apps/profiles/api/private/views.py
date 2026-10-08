from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView

from apps.core.api.auth.permissions import IsFullAdmin
from apps.core.api.views.generics import UnpaginatedDataListMixin
from apps.identity.roles import SUPERUSER_ACCOUNT_MESSAGE, may_change_account
from apps.profiles import selectors, services
from apps.profiles.api.private.serializers import AdminTeacherOptionSerializer, AdminTeacherSerializer


class AdminTeacherView:
    permission_classes = [IsFullAdmin]

    def get_queryset(self):
        return selectors.admin_teachers()

    serializer_class = AdminTeacherSerializer

    def perform_destroy(self, instance):
        if not may_change_account(self.request.user, instance.user):
            raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        services.delete_teacher(instance)


class AdminTeacherListCreateAPIView(AdminTeacherView, ListCreateAPIView):
    search_fields = ["user__name", "designation"]


class AdminTeacherDetailAPIView(AdminTeacherView, RetrieveUpdateDestroyAPIView):
    pass


class AdminTeacherLookupAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Unpaginated picker for assigning a teacher to a course."""

    permission_classes = [IsFullAdmin]
    serializer_class = AdminTeacherOptionSerializer

    def get_queryset(self):
        return selectors.teacher_options()
