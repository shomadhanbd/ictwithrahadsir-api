from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.viewsets import UnpaginatedDataListMixin
from apps.core.streaming import stream_file
from apps.courses import selectors, services
from apps.courses.api.public.filters import PublicCourseFilter
from apps.courses.api.public.serializers import (
    ContentCompletionRequestSerializer,
    ContentDetailSerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseProgressSerializer,
)
from apps.courses.api.serializers import CourseMaterialSerializer
from apps.courses.models import Content, Course, CourseMaterial


class CourseCardsMixin:
    """Batches the card aggregates for whatever page of courses is being serialised."""

    def get_serializer(self, *args, **kwargs):
        if kwargs.get("many") and args:
            courses = list(args[0])
            kwargs["context"] = {
                **self.get_serializer_context(),
                "course_stats": selectors.course_card_stats(courses, self.request.user),
            }
            args = (courses, *args[1:])
        return super().get_serializer(*args, **kwargs)


class PublicCourseListAPIView(CourseCardsMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CourseListSerializer
    pagination_class = LaravelStylePageNumberPagination
    filterset_class = PublicCourseFilter
    search_fields = ["title", "subtitle", "summary"]
    ordering_fields = ["published_at", "title", "starts_on"]
    ordering = ["-is_featured", "-published_at", "-id"]

    def get_queryset(self):
        return Course.objects.published().visible_to(self.request.user).with_catalogue_prefetch()


class PublicCourseDetailAPIView(APIView):
    """Staff may preview any course; enrolled students keep access after archiving."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        course = selectors.course_for_viewer(request.user, slug)
        context = {"request": request, "course_stats": selectors.course_card_stats([course], request.user)}
        return Response(CourseDetailSerializer(course, context=context).data)


class MyCourseListAPIView(CourseCardsMixin, UnpaginatedDataListMixin, ListAPIView):
    """Courses the caller is enrolled on, archived ones included."""

    permission_classes = [IsAuthenticated]
    serializer_class = CourseListSerializer
    queryset = Course.objects.none()

    def get_queryset(self):
        return selectors.enrolled_courses(self.request.user)


class ContentDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        content = selectors.accessible_content(request.user, slug)
        return Response(ContentDetailSerializer(content, context={"request": request}).data)


class ContentPdfAPIView(APIView):
    """Streams the PDF so its URL is never exposed."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        content = selectors.accessible_content(request.user, slug, type=Content.Type.PDF)
        if not content.pdf_file:
            raise NotFound("PDF not found.")
        return stream_file(
            content.pdf_file,
            filename=f"{content.slug}.pdf",
            range_header=request.headers.get("Range"),
            content_type="application/pdf",
            missing="PDF not found.",
        )


class CourseProgressAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _payload(self, course):
        return {"data": CourseProgressSerializer(selectors.course_progress(user=self.request.user, course=course)).data}

    def _content_id(self, request):
        body = ContentCompletionRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        return body.validated_data["content_id"]

    def get(self, request, slug):
        return Response(self._payload(selectors.enrolled_course(request.user, slug)))

    def post(self, request, slug):
        course = selectors.enrolled_course(request.user, slug)
        services.complete_lesson_by_hand(user=request.user, course=course, content_id=self._content_id(request))
        return Response(self._payload(course), status=status.HTTP_201_CREATED)

    def delete(self, request, slug):
        course = selectors.enrolled_course(request.user, slug)
        services.uncomplete_lesson(user=request.user, course=course, content_id=self._content_id(request))
        return Response(self._payload(course))


class CourseMaterialListAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Supplementary files for a course the caller is enrolled on."""

    permission_classes = [IsAuthenticated]
    serializer_class = CourseMaterialSerializer
    queryset = CourseMaterial.objects.none()

    def get_queryset(self):
        course = selectors.enrolled_course(self.request.user, self.kwargs["slug"])
        return CourseMaterial.objects.filter(course=course).order_by("-created_at")
