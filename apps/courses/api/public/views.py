from django.http import StreamingHttpResponse

import requests
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.viewsets import (
    CourseScopedAdminMixin,  # noqa: F401
    SchemaSafeQuerysetMixin,
    UnpaginatedDataListMixin,
)
from apps.courses.api.serializers import (
    ContentCompletionRequestSerializer,
    ContentDetailSerializer,
    CourseCategorySerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseMaterialSerializer,
    CourseProgressSerializer,
    build_category_children,
    build_course_stats,
)
from apps.courses.models import (
    Content,
    ContentCompletion,
    Course,
    CourseCategory,
    CourseMaterial,
    Enrollment,
)
from apps.courses.selectors import course_progress

TRUTHY = ('1', 'true', 'True')


class CourseListContextMixin:
    """Serialises a page of courses without a per-course query storm.

    `Course.objects.with_catalogue_prefetch()` collapses the m2m/reverse
    lookups to one query each for the whole page, and `build_course_stats`
    does the same for the aggregates the serializer computes itself.
    """

    def get_serializer_context(self):
        context = super().get_serializer_context()
        page = getattr(self, '_page_for_stats', None)
        if page is not None:
            context['course_stats'] = build_course_stats(page, self.request)
        return context

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        self._page_for_stats = page if page is not None else list(queryset)
        return page

    def list(self, request, *args, **kwargs):
        # Populated by paginate_queryset for paginated views; unpaginated
        # subclasses set it themselves before serialising.
        return super().list(request, *args, **kwargs)


class PublicCourseListAPIView(CourseListContextMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CourseListSerializer
    pagination_class = LaravelStylePageNumberPagination

    def get_queryset(self):
        qs = Course.objects.active().with_catalogue_prefetch()

        is_online = self.request.query_params.get('is_online')
        if is_online is not None:
            qs = qs.filter(is_online=is_online in TRUTHY)

        category_slug = self.request.query_params.get('category_slug')
        if category_slug:
            qs = qs.filter(categories__slug=category_slug)

        return qs.distinct()


class PublicCourseDetailAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='One course by slug', responses={200: CourseDetailSerializer})
    def get(self, request, slug):
        course = Course.objects.filter(slug=slug, active=True).with_catalogue_prefetch().first()
        if not course:
            raise NotFound('Course not found.')

        # Detail inherits every field the list serializer computes, so it
        # inherits the same six COUNTs and the price/enrolment lookups. It
        # was the one course endpoint not going through the batcher.
        return Response(
            CourseDetailSerializer(
                course,
                context={
                    'request': request,
                    'course_stats': build_course_stats([course], request),
                },
            ).data
        )


class BaseContentAPIView(APIView):
    """Shared lookup + access check for the content endpoints."""

    permission_classes = [AllowAny]

    def get_accessible_content(self, slug):
        # The detail payload reads the linked Exam for exam content.
        content = Content.objects.filter(slug=slug, active=True).first()
        if not content:
            raise NotFound('Content not found.')
        if not content.is_accessible_by(self.request.user):
            raise PermissionDenied('Not subscribed')
        return content


class ContentDetailAPIView(BaseContentAPIView):
    @extend_schema(summary='One lesson by slug', responses={200: ContentDetailSerializer})
    def get(self, request, slug):
        content = self.get_accessible_content(slug)
        return Response(ContentDetailSerializer(content, context={'request': request}).data)


class ContentPdfAPIView(BaseContentAPIView):
    """Streams the stored PDF through the API so the file URL is never
    handed to a client that is not entitled to it."""

    CHUNK_SIZE = 8192
    UPSTREAM_TIMEOUT_SECONDS = 30

    @extend_schema(
        summary='Stream a lesson PDF',
        responses={(200, 'application/pdf'): OpenApiResponse(description='The PDF bytes.')},
    )
    def get(self, request, slug):
        content = Content.objects.filter(slug=slug, active=True).first()
        if not content or content.type != Content.Type.PDF:
            raise NotFound('PDF not found.')
        if not content.is_accessible_by(request.user):
            raise PermissionDenied('Not subscribed')
        if not content.pdf_file:
            raise NotFound('PDF not found.')

        upstream = requests.get(content.pdf_file, stream=True, timeout=self.UPSTREAM_TIMEOUT_SECONDS)
        response = StreamingHttpResponse(
            upstream.iter_content(chunk_size=self.CHUNK_SIZE),
            content_type=upstream.headers.get('Content-Type', 'application/pdf'),
        )
        response['Content-Disposition'] = f'inline; filename="{content.slug}.pdf"'
        return response


class MyCourseListAPIView(SchemaSafeQuerysetMixin, UnpaginatedDataListMixin, CourseListContextMixin, ListAPIView):
    """Courses the caller is enrolled on."""

    permission_classes = [IsAuthenticated]
    serializer_class = CourseListSerializer
    queryset = Course.objects.none()

    def get_queryset(self):
        course_ids = Enrollment.objects.for_user(self.request.user).values_list('course_id', flat=True)
        return Course.objects.filter(id__in=course_ids).active().with_catalogue_prefetch()

    def get_list_payload(self, request, *args, **kwargs):
        # Set before serialising so CourseListContextMixin can batch the
        # per-course aggregates for the whole unpaginated list.
        courses = list(self.get_queryset())
        self._page_for_stats = courses
        return self.get_serializer(courses, many=True).data


def _current_enrollment(user, course):
    """The caller's live enrolment on a course, or None.

    The expiry rule itself lives on `EnrollmentQuerySet.current()`, so
    progress, materials and content access cannot disagree about who is
    still enrolled.
    """
    return Enrollment.objects.filter(course=course, user=user).current().first()


class CourseProgressAPIView(APIView):
    """How far the caller has got on a course.

    GET returns the completed content ids plus a count, so the client can both
    tick individual lessons and draw a bar without a second request. POST marks
    one lesson done, DELETE un-marks it — a student who ticked the wrong row
    should be able to take it back.

    The total counts every active content on the course, so a course that gains
    a lesson correctly drops everyone's percentage rather than leaving people
    permanently at 100%.
    """

    permission_classes = [IsAuthenticated]

    def _course(self, slug):
        course = Course.objects.filter(slug=slug, active=True).first()
        if not course:
            raise NotFound('Course not found.')
        if not _current_enrollment(self.request.user, course):
            raise PermissionDenied('You are not enrolled on this course.')
        return course

    def _payload(self, course):
        return {'data': CourseProgressSerializer(course_progress(user=self.request.user, course=course)).data}

    @extend_schema(
        summary='Progress through a course',
        responses={200: OpenApiResponse(CourseProgressSerializer, description='`{data: {...}}`')},
    )
    def get(self, request, slug):
        return Response(self._payload(self._course(slug)))

    @extend_schema(
        summary='Mark a lesson complete',
        request=ContentCompletionRequestSerializer,
        responses={201: OpenApiResponse(CourseProgressSerializer, description='`{data: {...}}`')},
    )
    def post(self, request, slug):
        course = self._course(slug)
        serializer = ContentCompletionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = Content.objects.filter(pk=serializer.validated_data['content_id'], course=course).active().first()
        if not content:
            raise ValidationError({'content_id': ['Unknown content for this course.']})

        ContentCompletion.objects.get_or_create(user=request.user, content=content, defaults={'course': course})
        return Response(self._payload(course), status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Un-mark a lesson',
        request=ContentCompletionRequestSerializer,
        responses={200: OpenApiResponse(CourseProgressSerializer, description='`{data: {...}}`')},
    )
    def delete(self, request, slug):
        course = self._course(slug)
        # No serializer here: an unparseable id simply matches no completion,
        # and un-ticking something that was never ticked is not an error.
        ContentCompletion.objects.filter(
            user=request.user,
            course=course,
            content_id=request.data.get('content_id'),
        ).delete()
        return Response(self._payload(course))


class CourseMaterialListAPIView(SchemaSafeQuerysetMixin, UnpaginatedDataListMixin, ListAPIView):
    """Supplementary files for a course the caller is enrolled on.

    The admin has managed these all along (`admin/course-materials/`) with no
    public route, so a lecture sheet uploaded for a course reached nobody. It
    is enrolment-gated rather than open: these are the same class of asset as a
    paid Content, and the course player is the only place they make sense.

    Gating reuses `Enrollment` with the expiry check `Content.is_accessible_by`
    applies, so a lapsed subscription loses the materials at the same moment it
    loses the lessons.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CourseMaterialSerializer
    queryset = CourseMaterial.objects.none()

    def get_queryset(self):
        course = Course.objects.filter(slug=self.kwargs['slug']).active().first()
        if not course:
            raise NotFound('Course not found.')

        if not _current_enrollment(self.request.user, course):
            raise PermissionDenied('You are not enrolled on this course.')

        return CourseMaterial.objects.filter(course=course).order_by('-created_at')


class PublicCourseCategoryListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CourseCategorySerializer
    queryset = CourseCategory.objects.filter(category__isnull=True)

    def get_list_payload(self, request, *args, **kwargs):
        roots = list(self.get_queryset())
        return self.get_serializer(
            roots,
            many=True,
            context={
                **self.get_serializer_context(),
                'category_children': build_category_children(roots),
            },
        ).data
