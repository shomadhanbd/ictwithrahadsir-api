from rest_framework.generics import ListAPIView

from apps.core.api.permissions import IsFullAdmin
from apps.core.api.viewsets import AdminModelViewSet, UnpaginatedDataListMixin
from apps.faculty.api.v1.filters import InstructorFilter
from apps.faculty.api.v1.serializers import (
    AdminTeacherSerializer,
    InstructorSerializer,
    TeacherSerializer,
)
from apps.faculty.models import CourseInstructor, Teacher


class AdminTeamViewSet(AdminModelViewSet):
    """Full CRUD at /admin/team -- the Teachers page in the admin panel."""
    permission_classes = [IsFullAdmin]

    queryset = Teacher.objects.select_related('user')
    serializer_class = AdminTeacherSerializer
    # Without this the global SearchFilter has nothing to match on, so
    # `?search=` was accepted and silently ignored -- the admin panel's
    # search box returned the unfiltered list and looked broken.
    search_fields = ['name', 'designation']



class AdminTeacherLookupAPIView(UnpaginatedDataListMixin, ListAPIView):
    """GET /admin/teacher -- unpaginated lookup used when assigning an
    instructor to a course."""

    permission_classes = [IsFullAdmin]
    serializer_class = TeacherSerializer
    queryset = Teacher.objects.all()


class AdminInstructorViewSet(AdminModelViewSet):
    permission_classes = [IsFullAdmin]
    queryset = CourseInstructor.objects.select_related('teacher').all()
    serializer_class = InstructorSerializer
    search_fields = ['name', 'designation', 'institute', 'email']
    filterset_class = InstructorFilter
