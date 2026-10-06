from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView

from apps.core.api.auth.permissions import SUPERUSER_ACCOUNT_MESSAGE, IsFullAdmin, may_change_account
from apps.core.api.views.generics import UnpaginatedDataListMixin
from apps.profiles import services
from apps.profiles.api.private.serializers import AdminTeacherOptionSerializer, AdminTeacherSerializer
from apps.profiles.models import TeacherProfile


class AdminTeacherView:
    permission_classes = [IsFullAdmin]
    queryset = TeacherProfile.objects.roster()
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
    queryset = TeacherProfile.objects.select_related("user")
