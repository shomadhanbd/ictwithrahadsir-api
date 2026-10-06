from rest_framework.generics import ListAPIView

from apps.core.api.permissions import IsFullAdmin
from apps.core.api.viewsets import AdminModelViewSet, UnpaginatedDataListMixin
from apps.profiles import services
from apps.profiles.api.private.serializers import AdminTeacherSerializer
from apps.profiles.models import TeacherProfile


class AdminTeacherViewSet(AdminModelViewSet):
    permission_classes = [IsFullAdmin]
    queryset = TeacherProfile.objects.roster()
    serializer_class = AdminTeacherSerializer
    search_fields = ["user__name", "designation"]

    def perform_destroy(self, instance):
        services.delete_teacher(instance)


class AdminTeacherLookupAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Unpaginated picker for assigning a teacher to a course."""

    permission_classes = [IsFullAdmin]
    serializer_class = AdminTeacherSerializer
    queryset = TeacherProfile.objects.roster()
