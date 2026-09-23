from rest_framework.generics import ListAPIView

from apps.core.api.permissions import IsFullAdmin
from apps.core.api.viewsets import AdminModelViewSet, UnpaginatedDataListMixin
from apps.profiles.api.private.serializers import AdminTeacherSerializer
from apps.profiles.models import TeacherProfile

#: Read through the account it belongs to, with its subjects and classes.
#: Without this each row costs three more queries.
ROSTER = TeacherProfile.objects.select_related('user').prefetch_related('subjects', 'levels')


class AdminTeacherViewSet(AdminModelViewSet):
    """Full CRUD at /admin/teachers -- the Teachers page in the admin panel."""

    permission_classes = [IsFullAdmin]
    queryset = ROSTER
    serializer_class = AdminTeacherSerializer
    #: Without these the global SearchFilter has nothing to match on, and
    #: `?search=` is accepted then silently ignored.
    search_fields = ['user__name', 'designation']


class AdminTeacherLookupAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Unpaginated lookup, used when assigning a teacher to a course.

    Serves the admin serializer so the picker can show which account each
    teacher holds; the public key list stays frozen.
    """

    permission_classes = [IsFullAdmin]
    serializer_class = AdminTeacherSerializer
    queryset = ROSTER
