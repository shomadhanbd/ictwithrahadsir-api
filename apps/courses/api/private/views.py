from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.auth.permissions import IsFullAdmin, IsTeachingStaff
from apps.core.api.views.exports import csv_response
from apps.courses import selectors, services
from apps.courses.api.permissions import (
    CourseScopedAdminMixin,
    IsCourseTeacherAdminDeletes,
    assert_may_manage_course,
)
from apps.courses.api.private.filters import (
    AdminCourseFilter,
    ContentFilter,
    CourseTeacherFilter,
    RoutineFilter,
    SectionFilter,
)
from apps.courses.api.private.serializers import (
    AdminContentSerializer,
    AdminCourseSerializer,
    AdminCourseTeacherSerializer,
    AdminEnrollmentCreateSerializer,
    AdminEnrollmentRequestSerializer,
    AdminSectionSerializer,
    ContentToggleSerializer,
    EnrollmentSerializer,
    SectionMoveSerializer,
)
from apps.courses.api.serializers import RoutineSerializer
from apps.courses.exports import STUDENT_EXPORT_HEADER, student_export_rows
from apps.courses.models import Content, Course, Enrollment, Routine, Section


class AdminCourseView(CourseScopedAdminMixin):
    permission_classes = [IsCourseTeacherAdminDeletes]
    course_field = "id"
    # A class attribute, not get_queryset(): CourseScopedAdminMixin narrows it to the teacher's own courses.
    queryset = selectors.admin_courses()

    serializer_class = AdminCourseSerializer

    def perform_destroy(self, instance):
        services.delete_course(instance)


class AdminCourseListCreateAPIView(AdminCourseView, ListCreateAPIView):
    search_fields = ["title", "subtitle", "slug"]
    filterset_class = AdminCourseFilter


class AdminCourseDetailAPIView(AdminCourseView, RetrieveUpdateDestroyAPIView):
    pass


class AdminRoutineView(CourseScopedAdminMixin):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = Routine.objects.all()
    serializer_class = RoutineSerializer


class AdminRoutineListCreateAPIView(AdminRoutineView, ListCreateAPIView):
    search_fields = ["title"]
    filterset_class = RoutineFilter


class AdminRoutineDetailAPIView(AdminRoutineView, RetrieveUpdateDestroyAPIView):
    pass


class AdminSectionView(CourseScopedAdminMixin):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = Section.objects.all()
    serializer_class = AdminSectionSerializer


class AdminSectionListCreateAPIView(AdminSectionView, ListCreateAPIView):
    search_fields = ["title"]
    filterset_class = SectionFilter


class AdminSectionDetailAPIView(AdminSectionView, RetrieveUpdateDestroyAPIView):
    pass


class AdminSectionMoveAPIView(AdminSectionView, GenericAPIView):
    """Swaps a section with its neighbour among its siblings."""

    def post(self, request, *args, **kwargs):
        section = self.get_object()
        body = SectionMoveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.move_section(section, direction=body.validated_data["direction"])
        section.refresh_from_db()
        return Response(AdminSectionSerializer(section).data)


class AdminContentView(CourseScopedAdminMixin):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = selectors.admin_contents()

    serializer_class = AdminContentSerializer


class AdminContentListCreateAPIView(AdminContentView, ListCreateAPIView):
    search_fields = ["title"]
    filterset_class = ContentFilter


class AdminContentDetailAPIView(AdminContentView, RetrieveUpdateDestroyAPIView):
    pass


class AdminContentToggleAPIView(APIView):
    """Flips `active` or `paid` on a lesson."""

    permission_classes = [IsTeachingStaff]

    def post(self, request, pk):
        content = get_object_or_404(Content, pk=pk)
        assert_may_manage_course(request, content.course_id)
        body = ContentToggleSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.toggle_content_flag(content, body.validated_data["action"])
        return Response(AdminContentSerializer(content).data)


class AdminCourseEnrolledUserListAPIView(ListAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.none()
    search_fields = ["user__name", "user__phone", "user__email"]

    def get_queryset(self):
        assert_may_manage_course(self.request, int(self.kwargs["pk"]))
        return selectors.course_enrollments(self.kwargs["pk"])


class AdminCourseStudentsExportAPIView(APIView):
    """The course's students as a CSV that opens cleanly in Excel."""

    permission_classes = [IsTeachingStaff]

    def get(self, request, pk):
        assert_may_manage_course(request, pk)
        course = get_object_or_404(Course, pk=pk)
        rows = student_export_rows(selectors.course_students_export(course))
        return csv_response(f"{course.slug}-students.csv", STUDENT_EXPORT_HEADER, rows)


class AdminEnrollmentAPIView(APIView):
    """Attach (POST), amend (PATCH) or remove (DELETE) a student's enrolment.

    Admins only: a free or extended enrolment is access nobody paid for, and removing one ends paid access.
    """

    permission_classes = [IsFullAdmin]

    def _body(self, request, serializer_class=AdminEnrollmentRequestSerializer):
        body = serializer_class(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if data["course"] is not None:
            assert_may_manage_course(request, data["course"].pk)
        return data

    def post(self, request):
        data = self._body(request, AdminEnrollmentCreateSerializer)
        enrollment = services.grant_course_access(
            user=data["user"],
            course=data["course"],
            payment_type=Enrollment.PaymentType.FREE,
            valid_till=data.get("valid_till"),
        )
        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        data = self._body(request)
        enrollment = selectors.enrollment_of(data["course"], data.get("user_id")) if data["course"] else None
        if not enrollment:
            raise NotFound("Enrollment not found.")
        services.update_enrollment(enrollment, data)
        return Response(EnrollmentSerializer(enrollment).data)

    def delete(self, request):
        data = self._body(request)
        course = data["course"]
        removed = bool(course) and services.revoke_course_access(user_id=data.get("user_id"), course=course)
        return Response({"ok": removed})


class AdminCourseTeacherView:
    permission_classes = [IsFullAdmin]

    def get_queryset(self):
        return selectors.admin_course_teachers()

    serializer_class = AdminCourseTeacherSerializer


class AdminCourseTeacherListCreateAPIView(AdminCourseTeacherView, ListCreateAPIView):
    search_fields = ["user__name", "user__email", "user__teacher__designation", "user__teacher__institute"]
    filterset_class = CourseTeacherFilter


class AdminCourseTeacherDetailAPIView(AdminCourseTeacherView, RetrieveUpdateDestroyAPIView):
    pass
