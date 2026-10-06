from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsFullAdmin, IsTeachingStaff
from apps.core.api.responses import OkResponseSerializer
from apps.core.api.viewsets import AdminModelViewSet, SlugOrPkLookupMixin
from apps.core.exports import csv_response
from apps.courses import selectors, services
from apps.courses.api.permissions import (
    CourseScopedAdminMixin,
    IsCourseTeacherAdminDeletes,
    assert_may_manage_course,
)
from apps.courses.api.private.filters import (
    AdminCourseFilter,
    ContentFilter,
    CourseMaterialFilter,
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
from apps.courses.api.serializers import CourseMaterialSerializer, RoutineSerializer
from apps.courses.exports import STUDENT_EXPORT_HEADER, student_export_rows
from apps.courses.models import Content, Course, CourseMaterial, CourseTeacher, Enrollment, Routine, Section


class AdminCourseViewSet(SlugOrPkLookupMixin, CourseScopedAdminMixin, AdminModelViewSet):
    permission_classes = [IsCourseTeacherAdminDeletes]
    course_field = "id"
    queryset = Course.objects.select_related("class_level", "group", "batch").with_enrolled_count()
    serializer_class = AdminCourseSerializer
    lookup_field = "slug"
    search_fields = ["title", "subtitle", "slug"]
    filterset_class = AdminCourseFilter

    def perform_destroy(self, instance):
        services.delete_course(instance)


class AdminRoutineViewSet(CourseScopedAdminMixin, AdminModelViewSet):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = Routine.objects.all()
    serializer_class = RoutineSerializer
    search_fields = ["title"]
    filterset_class = RoutineFilter


class AdminSectionViewSet(SlugOrPkLookupMixin, CourseScopedAdminMixin, AdminModelViewSet):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = Section.objects.all()
    serializer_class = AdminSectionSerializer
    lookup_field = "slug"
    search_fields = ["title"]
    filterset_class = SectionFilter

    @action(detail=True, methods=["post"])
    def move(self, request, *args, **kwargs):
        section = self.get_object()
        body = SectionMoveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.move_section(section, direction=body.validated_data["direction"])
        section.refresh_from_db()
        return Response(AdminSectionSerializer(section).data)


class AdminContentViewSet(CourseScopedAdminMixin, AdminModelViewSet):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = Content.objects.select_related("exam").prefetch_related("exam__sections")
    serializer_class = AdminContentSerializer
    lookup_field = "slug"
    search_fields = ["title"]
    filterset_class = ContentFilter


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
    pagination_class = LaravelStylePageNumberPagination
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
        enrollment = (
            Enrollment.objects.filter(course=data["course"], user_id=data.get("user_id")).first()
            if data["course"]
            else None
        )
        if not enrollment:
            raise NotFound("Enrollment not found.")
        services.update_enrollment(enrollment, data)
        return Response(EnrollmentSerializer(enrollment).data)

    def delete(self, request):
        data = self._body(request)
        course = data["course"]
        removed = bool(course) and services.revoke_course_access(user_id=data.get("user_id"), course=course)
        return Response(OkResponseSerializer({"ok": removed}).data)


class AdminCourseMaterialViewSet(CourseScopedAdminMixin, AdminModelViewSet):
    permission_classes = [IsCourseTeacherAdminDeletes]
    queryset = CourseMaterial.objects.select_related("course").order_by("-id")
    serializer_class = CourseMaterialSerializer
    search_fields = ["title", "type", "course__title"]
    filterset_class = CourseMaterialFilter


class AdminCourseTeacherViewSet(AdminModelViewSet):
    permission_classes = [IsFullAdmin]
    queryset = CourseTeacher.objects.select_related("user__teacher", "course")
    serializer_class = AdminCourseTeacherSerializer
    search_fields = [
        "user__name",
        "user__email",
        "user__teacher__designation",
        "user__teacher__institute",
    ]
    filterset_class = CourseTeacherFilter
