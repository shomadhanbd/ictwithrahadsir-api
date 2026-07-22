from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.core.permissions import IsAdminRole
from apps.core.viewsets import AdminModelViewSet

from .models import Teacher
from .serializers import TeacherSerializer


class AdminTeamViewSet(AdminModelViewSet):
    """Full CRUD at /admin/team -- the Teachers page in the admin panel."""

    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_teacher_lookup(request):
    """GET /admin/teacher -- simple unpaginated lookup used when assigning
    an instructor to a course."""
    qs = Teacher.objects.all()
    return Response({"data": TeacherSerializer(qs, many=True).data})
