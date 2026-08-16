import requests
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.models import User
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet
from apps.courses.api.v1.serializers import (
    AdminContentSerializer,
    AdminCourseSerializer,
    AdminSectionSerializer,
    ContentDetailSerializer,
    CourseCategorySerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CoursePriceSerializer,
    CouponSerializer,
    CourseUserSerializer,
    InstructorSerializer,
    RoutineSerializer,
    build_course_stats,
)
from apps.courses.models import (
    Content,
    Course,
    CourseCategory,
    CoursePrice,
    CourseUser,
    Coupon,
    Instructor,
    Routine,
    Section,
)

TRUTHY = ('1', 'true', 'True')

# ---------------------------------------------------------------------------
# Public / client-facing
# ---------------------------------------------------------------------------


class CourseListContextMixin:
    """Serialises a page of courses without a per-course query storm.

    `prefetch_related` collapses the m2m/reverse lookups to one query each
    for the whole page, and `build_course_stats` does the same for the
    aggregates the serializer computes itself.
    """

    PREFETCH = ('categories', 'instructors', 'routines')

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
        qs = Course.objects.filter(active=True).prefetch_related(*self.PREFETCH)

        is_online = self.request.query_params.get('is_online')
        if is_online is not None:
            qs = qs.filter(is_online=is_online in TRUTHY)

        category_slug = self.request.query_params.get('category_slug')
        if category_slug:
            qs = qs.filter(categories__slug=category_slug)

        return qs.distinct()


class PublicCourseDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        course = Course.objects.filter(slug=slug, active=True).first()
        if not course:
            raise NotFound('Course not found.')
        return Response(CourseDetailSerializer(course, context={'request': request}).data)


class BaseContentAPIView(APIView):
    """Shared lookup + access check for the content endpoints."""

    permission_classes = [AllowAny]

    def get_accessible_content(self, slug):
        content = Content.objects.filter(slug=slug, active=True).first()
        if not content:
            raise NotFound('Content not found.')
        if not content.is_accessible_by(self.request.user):
            raise PermissionDenied('Not subscribed')
        return content


class ContentDetailAPIView(BaseContentAPIView):
    def get(self, request, slug):
        content = self.get_accessible_content(slug)
        return Response(ContentDetailSerializer(content, context={'request': request}).data)


class ContentPdfAPIView(BaseContentAPIView):
    """Streams the stored PDF through the API so the file URL is never
    handed to a client that is not entitled to it."""

    CHUNK_SIZE = 8192
    UPSTREAM_TIMEOUT_SECONDS = 30

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


class MyCourseListAPIView(CourseListContextMixin, ListAPIView):
    """Courses the caller is enrolled on."""

    permission_classes = [IsAuthenticated]
    serializer_class = CourseListSerializer
    pagination_class = None

    def get_queryset(self):
        course_ids = CourseUser.objects.filter(user=self.request.user).values_list(
            'course_id', flat=True
        )
        return Course.objects.filter(id__in=course_ids, active=True).prefetch_related(
            *self.PREFETCH
        )

    def list(self, request, *args, **kwargs):
        courses = list(self.get_queryset())
        self._page_for_stats = courses
        serializer = self.get_serializer(courses, many=True)
        return Response({'data': serializer.data})


class PublicCourseCategoryListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CourseCategorySerializer
    pagination_class = None
    queryset = CourseCategory.objects.filter(category__isnull=True)

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({'data': serializer.data})


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminCourseViewSet(AdminModelViewSet):
    queryset = Course.objects.all()
    serializer_class = AdminCourseSerializer
    lookup_field = 'slug'


class AdminCourseCategoryViewSet(AdminModelViewSet):
    queryset = CourseCategory.objects.all()
    serializer_class = CourseCategorySerializer
    lookup_field = 'slug'

    def get_queryset(self):
        qs = super().get_queryset()
        category_id = self.request.query_params.get('category_id')
        if category_id:
            return qs.filter(category_id=category_id)
        if self.action == 'list':
            return qs.filter(category__isnull=True)
        return qs


class AdminInstructorViewSet(AdminModelViewSet):
    queryset = Instructor.objects.all()
    serializer_class = InstructorSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminCoursePriceViewSet(AdminModelViewSet):
    queryset = CoursePrice.objects.all()
    serializer_class = CoursePriceSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        priceable_type = self.request.query_params.get('priceable_type')
        if priceable_type:
            qs = qs.filter(priceable_type=priceable_type)

        # The admin panel filters a course's prices with
        # `?priceable_type=course&course_id=<id>` -- course_id here means
        # "the priceable_id when priceable_type is course".
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(
                priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=course_id
            )
        return qs


class AdminCouponViewSet(AdminModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        price_id = self.request.query_params.get('price_id')
        if price_id:
            qs = qs.filter(price_id=price_id)
        return qs


class AdminRoutineViewSet(AdminModelViewSet):
    queryset = Routine.objects.all()
    serializer_class = RoutineSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminSectionViewSet(AdminModelViewSet):
    queryset = Section.objects.all()
    serializer_class = AdminSectionSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course_id')
        section_id = self.request.query_params.get('section_id')

        if course_id:
            qs = qs.filter(course_id=course_id)
        if section_id:
            qs = qs.filter(section_id=section_id)
        elif course_id and self.action == 'list':
            qs = qs.filter(section__isnull=True)
        return qs


class AdminContentViewSet(AdminModelViewSet):
    queryset = Content.objects.all()
    serializer_class = AdminContentSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        qs = super().get_queryset()
        section_id = self.request.query_params.get('section_id')
        if section_id:
            qs = qs.filter(section_id=section_id)
        return qs


class AdminContentToggleAPIView(APIView):
    """Flips `active` or `paid` on a piece of content.

    A GET that mutates, because that is what the admin panel already sends.
    """

    permission_classes = [IsAdminRole]
    TOGGLEABLE = ('active', 'paid')

    def get(self, request, pk):
        content = Content.objects.filter(pk=pk).first()
        if not content:
            raise NotFound('Content not found.')

        action = request.query_params.get('action')
        if action not in self.TOGGLEABLE:
            raise ValidationError({'action': ['Must be `active` or `paid`.']})

        setattr(content, action, not getattr(content, action))
        content.save(update_fields=[action])
        return Response(AdminContentSerializer(content).data)


class AdminCourseEnrolledUserListAPIView(ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = CourseUserSerializer
    pagination_class = LaravelStylePageNumberPagination

    def get_queryset(self):
        return CourseUser.objects.filter(course_id=self.kwargs['pk']).select_related('user')


class BaseCourseEnrollmentAPIView(APIView):
    """The admin panel identifies a course by `slugOrId` on the enrolment
    endpoints -- either the numeric id or the slug, never `course_id`."""

    permission_classes = [IsAdminRole]

    def get_course(self, data):
        value = data.get('slugOrId') or data.get('course_id')
        if value is None:
            return None
        value = str(value)
        if value.isdigit():
            return Course.objects.filter(pk=int(value)).first()
        return Course.objects.filter(slug=value).first()


class AdminEnrollmentAPIView(BaseCourseEnrollmentAPIView):
    """Attach, amend or remove a student's enrolment.

    One resource with a method per action. The legacy API exposed this as
    three POST-only endpoints (user-attach / user-update / user-remove);
    those names still route here through the subclasses below.
    """

    def post(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')
        if not course or not user_id:
            raise ValidationError({'user_id': ['A valid course and user_id are required.']})

        # Checked rather than left to the FK constraint, which surfaced an
        # unknown id as an IntegrityError 500 instead of a validation error.
        if not User.objects.filter(pk=user_id).exists():
            raise ValidationError({'user_id': ['No such user.']})

        # The admin UI only sends `price_id` on attach -- validity and payment
        # type are derived from that price's own rule, not supplied by the caller.
        valid_till = None
        payment_type = CourseUser.PaymentType.FREE

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
            payment_type = (
                CourseUser.PaymentType.FREE
                if price.amount == 0
                else CourseUser.PaymentType.PAID
            )
            if price.validity_type == CoursePrice.ValidityType.ABSOLUTE:
                valid_till = price.validity_time
            elif price.validity_duration:
                valid_till = timezone.now() + timezone.timedelta(days=price.validity_duration)

        enrollment, _ = CourseUser.objects.update_or_create(
            course=course,
            user_id=user_id,
            defaults={'valid_till': valid_till, 'payment_type': payment_type},
        )
        return Response(CourseUserSerializer(enrollment).data, status=status.HTTP_201_CREATED)


    def patch(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')
        enrollment = (
            CourseUser.objects.filter(course=course, user_id=user_id).first()
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
        return Response(CourseUserSerializer(enrollment).data)


    def delete(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')

        deleted = 0
        if course:
            deleted, _ = CourseUser.objects.filter(course=course, user_id=user_id).delete()
        return Response({'ok': deleted > 0})


# The legacy flat API exposed the three actions above as separate POST-only
# endpoints. These keep those paths working without duplicating the logic.


class AdminCourseUserAttachAPIView(AdminEnrollmentAPIView):
    pass


class AdminCourseUserUpdateAPIView(AdminEnrollmentAPIView):
    def post(self, request):
        return self.patch(request)


class AdminCourseUserRemoveAPIView(AdminEnrollmentAPIView):
    def post(self, request):
        return self.delete(request)


class AdminCourseUserImportAPIView(APIView):
    """Bulk-enrol existing students on a course from a spreadsheet of phones."""

    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        file = request.FILES.get('file')
        if not file:
            raise ValidationError({'file': ['An Excel file is required.']})

        import openpyxl

        workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
        rows = list(workbook.active.iter_rows(values_only=True))
        header = [str(c).strip().lower() if c else '' for c in rows[0]] if rows else []

        attached, missing = 0, 0
        for row in rows[1:]:
            record = dict(zip(header, row))
            phone = str(record.get('phone') or '').strip()
            user = User.objects.filter(phone=phone).first() if phone else None
            if not user:
                missing += 1
                continue

            CourseUser.objects.update_or_create(
                course_id=pk,
                user=user,
                defaults={'payment_type': CourseUser.PaymentType.FREE},
            )
            attached += 1

        return Response({'attached': attached, 'missing': missing})
