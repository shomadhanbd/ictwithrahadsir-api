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
from apps.core.api.permissions import (
    IsFullAdmin,
    IsTeachingStaff,
    assert_may_manage_course,
)
from apps.core.api.responses import OkResponseSerializer
from apps.core.api.viewsets import (
    AdminModelViewSet,
    CourseScopedAdminMixin,  # noqa: F401
    SchemaSafeQuerysetMixin,
    SlugOrPkLookupMixin,
    UnpaginatedDataListMixin,
)
from apps.core.spreadsheets import read_records
from apps.courses.api.v1.filters import (
    ContentFilter,
    CouponFilter,
    CourseMaterialFilter,
    CoursePriceFilter,
    RoutineFilter,
    SectionFilter,
)
from apps.courses.api.v1.serializers import (
    AdminContentSerializer,
    AdminCourseSerializer,
    AdminEnrollmentRequestSerializer,
    AdminSectionSerializer,
    ContentCompletionRequestSerializer,
    ContentDetailSerializer,
    CouponSerializer,
    CourseCategorySerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseMaterialSerializer,
    CoursePriceSerializer,
    CourseProgressSerializer,
    EnrollmentImportRequestSerializer,
    EnrollmentSerializer,
    RoutineSerializer,
    build_category_children,
    build_course_stats,
)
from apps.courses.models import (
    Content,
    ContentCompletion,
    Coupon,
    Course,
    CourseCategory,
    CourseMaterial,
    CoursePrice,
    Enrollment,
    Routine,
    Section,
)
from apps.courses.selectors import course_progress
from apps.courses.services import (
    grant_from_price,
    import_enrollments,
    revoke_course_access,
)
from apps.identity.models import User

TRUTHY = ('1', 'true', 'True')

# ---------------------------------------------------------------------------
# Public / client-facing
# ---------------------------------------------------------------------------


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
        course = (
            Course.objects.filter(slug=slug, active=True)
            .with_catalogue_prefetch()
            .first()
        )
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
        content = Content.objects.select_related('exam').filter(slug=slug, active=True).first()
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

        upstream = requests.get(
            content.pdf_file, stream=True, timeout=self.UPSTREAM_TIMEOUT_SECONDS
        )
        response = StreamingHttpResponse(
            upstream.iter_content(chunk_size=self.CHUNK_SIZE),
            content_type=upstream.headers.get('Content-Type', 'application/pdf'),
        )
        response['Content-Disposition'] = f'inline; filename="{content.slug}.pdf"'
        return response


class MyCourseListAPIView(
    SchemaSafeQuerysetMixin, UnpaginatedDataListMixin, CourseListContextMixin, ListAPIView
):
    """Courses the caller is enrolled on."""

    permission_classes = [IsAuthenticated]
    serializer_class = CourseListSerializer
    queryset = Course.objects.none()

    def get_queryset(self):
        course_ids = Enrollment.objects.for_user(self.request.user).values_list(
            'course_id', flat=True
        )
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
        return {'data': CourseProgressSerializer(
            course_progress(user=self.request.user, course=course)
        ).data}

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

        content = Content.objects.filter(
            pk=serializer.validated_data['content_id'], course=course
        ).active().first()
        if not content:
            raise ValidationError({'content_id': ['Unknown content for this course.']})

        ContentCompletion.objects.get_or_create(
            user=request.user, content=content, defaults={'course': course}
        )
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


class CourseMaterialListAPIView(
    SchemaSafeQuerysetMixin, UnpaginatedDataListMixin, ListAPIView
):
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
            roots, many=True, context={
                **self.get_serializer_context(),
                'category_children': build_category_children(roots),
            }
        ).data


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminCourseViewSet(SlugOrPkLookupMixin, CourseScopedAdminMixin, AdminModelViewSet):
    # A course is its own owner, so the scoping column is the pk.
    course_field = 'id'
    # `categories` is a m2m on the serializer, so it is one query per course
    # on the list without this.
    queryset = Course.objects.prefetch_related('categories')
    serializer_class = AdminCourseSerializer
    lookup_field = 'slug'
    # Without this the global SearchFilter has nothing to match on, so
    # `?search=` was accepted and silently ignored -- the admin panel's
    # search box returned the unfiltered list and looked broken.
    search_fields = ['title', 'subtitle', 'slug']



class AdminCourseCategoryViewSet(SlugOrPkLookupMixin, AdminModelViewSet):
    permission_classes = [IsTeachingStaff]
    queryset = CourseCategory.objects.all()
    serializer_class = CourseCategorySerializer
    lookup_field = 'slug'
    search_fields = ['title']

    def get_queryset(self):
        qs = super().get_queryset()
        category_id = self.request.query_params.get('category_id')
        if category_id:
            return qs.filter(category_id=category_id)
        if self.action == 'list':
            return qs.filter(category__isnull=True)
        return qs


class AdminCoursePriceViewSet(AdminModelViewSet):
    permission_classes = [IsFullAdmin]
    queryset = CoursePrice.objects.all()
    serializer_class = CoursePriceSerializer
    search_fields = ['title']
    filterset_class = CoursePriceFilter


class AdminCouponViewSet(AdminModelViewSet):
    permission_classes = [IsFullAdmin]
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    filterset_class = CouponFilter


class AdminRoutineViewSet(CourseScopedAdminMixin, AdminModelViewSet):
    queryset = Routine.objects.all()
    serializer_class = RoutineSerializer
    search_fields = ['title']
    filterset_class = RoutineFilter


class AdminSectionViewSet(SlugOrPkLookupMixin, CourseScopedAdminMixin, AdminModelViewSet):
    queryset = Section.objects.all()
    serializer_class = AdminSectionSerializer
    lookup_field = 'slug'
    # Same inert-SearchFilter problem as the other admin lists: the panel
    # ships a search box against this endpoint, which did nothing without it.
    search_fields = ['title']
    filterset_class = SectionFilter

    def get_queryset(self):
        qs = super().get_queryset()
        # `course_id`/`section_id` are handled by the filterset. This is the
        # part it cannot express: listing a course's sections shows only the
        # top level, so the panel can expand the tree lazily. It depends on
        # the action rather than on a parameter.
        params = self.request.query_params
        if params.get('course_id') and not params.get('section_id') and self.action == 'list':
            qs = qs.filter(section__isnull=True)
        return qs


class AdminContentViewSet(CourseScopedAdminMixin, AdminModelViewSet):
    # The serializer merges the flat `exam_*` keys in from the related Exam
    # row on every content, exam or not -- a reverse one-to-one, so it is a
    # query each without this.
    queryset = Content.objects.select_related('exam')
    serializer_class = AdminContentSerializer
    lookup_field = 'slug'
    # The last admin list whose search box posted `?search=` into an inert
    # SearchFilter -- every sibling viewset got this during the redesign and
    # this one was missed, so typing in the lessons search did nothing.
    search_fields = ['title']
    filterset_class = ContentFilter


class AdminContentToggleAPIView(APIView):
    """Flips `active` or `paid` on a piece of content.

    A GET that mutates, because that is what the admin panel already sends.
    """

    permission_classes = [IsTeachingStaff]
    TOGGLEABLE = ('active', 'paid')

    @extend_schema(summary='Toggle a lesson\'s active/paid flag', responses={200: AdminContentSerializer})
    def get(self, request, pk):
        content = Content.objects.filter(pk=pk).first()
        if not content:
            raise NotFound('Content not found.')
        # Fetched by hand, so DRF never ran an object permission for it.
        assert_may_manage_course(request, content.course_id)

        action = request.query_params.get('action')
        if action not in self.TOGGLEABLE:
            raise ValidationError({'action': ['Must be `active` or `paid`.']})

        setattr(content, action, not getattr(content, action))
        content.save(update_fields=[action])
        return Response(AdminContentSerializer(content).data)


class AdminCourseEnrolledUserListAPIView(SchemaSafeQuerysetMixin, ListAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = EnrollmentSerializer
    pagination_class = LaravelStylePageNumberPagination
    # Never used directly -- `get_queryset` replaces it. Declared so the
    # schema generator can still identify the model (see
    # SchemaSafeQuerysetMixin).
    queryset = Enrollment.objects.none()
    # The panel's student search box posts `?search=`; without these the
    # global SearchFilter matches on nothing and silently returns everyone.
    search_fields = ['user__name', 'user__phone', 'user__email']

    def get_queryset(self):
        assert_may_manage_course(self.request, int(self.kwargs['pk']))
        # Explicitly ordered: an unordered queryset leaves the page boundaries
        # up to the database, so a student could appear on two pages or on
        # none. Newest enrolment first is also the useful default here.
        return (
            Enrollment.objects.filter(course_id=self.kwargs['pk'])
            .select_related('user')
            .order_by('-id')
        )


class BaseCourseEnrollmentAPIView(APIView):
    """The admin panel identifies a course by `slugOrId` on the enrolment
    endpoints -- either the numeric id or the slug, never `course_id`."""

    permission_classes = [IsTeachingStaff]

    def get_course(self, data):
        value = data.get('slugOrId') or data.get('course_id')
        if value is None:
            return None
        value = str(value)
        if value.isdigit():
            course = Course.objects.filter(pk=int(value)).first()
        else:
            course = Course.objects.filter(slug=value).first()
        if course is not None:
            # Enrolling somebody grants paid access, so it is scoped the same
            # way editing the course is.
            assert_may_manage_course(self.request, course.pk)
        return course


class AdminEnrollmentAPIView(BaseCourseEnrollmentAPIView):
    """Attach, amend or remove a student's enrolment.

    One resource with a method per action. The legacy API exposed this as
    three POST-only endpoints (user-attach / user-update / user-remove);
    those names still route here through the subclasses below.
    """

    @extend_schema(
        summary='Attach a student to a course',
        request=AdminEnrollmentRequestSerializer,
        responses={201: EnrollmentSerializer},
    )
    def post(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')
        if not course or not user_id:
            raise ValidationError({'user_id': ['A valid course and user_id are required.']})

        # Checked rather than left to the FK constraint, which surfaced an
        # unknown id as an IntegrityError 500 instead of a validation error.
        user = User.objects.filter(pk=user_id).first()
        if not user:
            raise ValidationError({'user_id': ['No such user.']})

        # The admin UI only sends `price_id` on attach -- validity and payment
        # type are derived from that price's own rule, not supplied by the
        # caller. `grant_from_price` owns that derivation; this endpoint only
        # has to resolve the price it applies.
        price = None
        price_id = request.data.get('price_id')
        if price_id:
            price = CoursePrice.objects.filter(
                pk=price_id,
                priceable_type=CoursePrice.PRICEABLE_COURSE,
                priceable_id=course.id,
            ).first()
            if not price:
                raise ValidationError(
                    {'price_id': ['This price does not belong to the selected course.']}
                )

        enrollment = grant_from_price(user=user, course=course, price=price)
        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)


    @extend_schema(
        summary='Amend an enrolment',
        request=AdminEnrollmentRequestSerializer,
        responses={200: EnrollmentSerializer},
    )
    def patch(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')
        enrollment = (
            Enrollment.objects.filter(course=course, user_id=user_id).first()
            if course
            else None
        )
        if not enrollment:
            raise NotFound('Enrollment not found.')

        if 'valid_till' in request.data:
            enrollment.valid_till = request.data.get('valid_till') or None
        if 'payment_type' in request.data:
            enrollment.payment_type = request.data.get('payment_type')
        enrollment.save()
        return Response(EnrollmentSerializer(enrollment).data)


    @extend_schema(
        summary='Remove an enrolment',
        request=AdminEnrollmentRequestSerializer,
        responses={200: OkResponseSerializer},
    )
    def delete(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')

        removed = bool(course) and revoke_course_access(user_id=user_id, course=course)
        return Response(OkResponseSerializer({'ok': removed}).data)


class AdminEnrollmentImportAPIView(APIView):
    """Bulk-enrol existing students on a course from a spreadsheet of phones."""

    permission_classes = [IsFullAdmin]

    @extend_schema(
        summary='Bulk-enrol students from a spreadsheet',
        request=EnrollmentImportRequestSerializer,
        responses={200: OpenApiResponse(description='`{attached, missing}`')},
    )
    def post(self, request, pk):
        course = Course.objects.filter(pk=pk).first()
        if not course:
            raise NotFound('Course not found.')

        serializer = EnrollmentImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        records = read_records(serializer.validated_data['file'])
        return Response(import_enrollments(course=course, records=records))


class AdminCourseMaterialViewSet(CourseScopedAdminMixin, AdminModelViewSet):
    """Materials were list-only: the admin panel could see them and nothing
    else. There was no way to add, rename or remove one from the panel at
    all, so the screen was a dead end."""

    # `course` is rendered on every row, so without this it is a query each.
    queryset = CourseMaterial.objects.select_related('course')
    serializer_class = CourseMaterialSerializer
    search_fields = ['title', 'type', 'course__title']
    filterset_class = CourseMaterialFilter

    def get_queryset(self):
        # Newest first, and explicitly ordered so pagination is stable.
        return super().get_queryset().order_by('-id')
