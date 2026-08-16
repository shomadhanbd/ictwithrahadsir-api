from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet
from apps.faculty.api.v1.serializers import InstructorSerializer, TeacherSerializer
from apps.faculty.models import CourseInstructor, Teacher


class AdminTeamViewSet(AdminModelViewSet):
    """Full CRUD at /admin/team -- the Teachers page in the admin panel."""

    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


class AdminTeacherLookupAPIView(ListAPIView):
    """GET /admin/teacher -- unpaginated lookup used when assigning an
    instructor to a course."""

    permission_classes = [IsAdminRole]
    serializer_class = TeacherSerializer
    queryset = Teacher.objects.all()
    pagination_class = None

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({'data': serializer.data})


class AdminInstructorViewSet(AdminModelViewSet):
    queryset = CourseInstructor.objects.select_related('teacher').all()
    serializer_class = InstructorSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs
