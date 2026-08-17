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
from apps.core.api.viewsets import AdminModelViewSet, SlugOrPkLookupMixin
from apps.courses.api.v1.serializers import (
    AdminContentSerializer,
    AdminCourseSerializer,
    AdminSectionSerializer,
    ContentDetailSerializer,
    CourseCategorySerializer,
    CourseDetailSerializer,
    CourseMaterialSerializer,
    CourseListSerializer,
    CoursePriceSerializer,
    CouponSerializer,
    EnrollmentSerializer,
    RoutineSerializer,
    build_category_children,
    build_course_stats,
)
from apps.courses.models import (
    Content,
    CourseMaterial,
    Course,
    CourseCategory,
    CoursePrice,
    Enrollment,
    Coupon,
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

    PREFETCH = ('categories', 'instructors__teacher', 'routines')

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
        course = (
            Course.objects.filter(slug=slug, active=True)
            .prefetch_related(*CourseListContextMixin.PREFETCH)
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
        course_ids = Enrollment.objects.filter(user=self.request.user).values_list(
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


class CourseMaterialListAPIView(ListAPIView):
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
    pagination_class = None

    def get_queryset(self):
        course = Course.objects.filter(slug=self.kwargs['slug'], active=True).first()
        if not course:
            raise NotFound('Course not found.')

        enrollment = Enrollment.objects.filter(
            course=course, user=self.request.user
        ).first()
        if not enrollment:
            raise PermissionDenied('You are not enrolled on this course.')
        if enrollment.valid_till and enrollment.valid_till < timezone.now():
            raise PermissionDenied('Your access to this course has expired.')

        return CourseMaterial.objects.filter(course=course).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        return Response({'data': self.get_serializer(self.get_queryset(), many=True).data})


class PublicCourseCategoryListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = CourseCategorySerializer
    pagination_class = None
    queryset = CourseCategory.objects.filter(category__isnull=True)

    def list(self, request, *args, **kwargs):
        roots = list(self.get_queryset())
        serializer = self.get_serializer(
            roots, many=True, context={
                **self.get_serializer_context(),
                'category_children': build_category_children(roots),
            }
        )
        return Response({'data': serializer.data})


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminCourseViewSet(SlugOrPkLookupMixin, AdminModelViewSet):
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
    queryset = CoursePrice.objects.all()
    serializer_class = CoursePriceSerializer
    search_fields = ['title']

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
    search_fields = ['title']

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminSectionViewSet(SlugOrPkLookupMixin, AdminModelViewSet):
    queryset = Section.objects.all()
    serializer_class = AdminSectionSerializer
    lookup_field = 'slug'
    # Same inert-SearchFilter problem as the other admin lists: the panel
    # ships a search box against this endpoint, which did nothing without it.
    search_fields = ['title']

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
    serializer_class = EnrollmentSerializer
    pagination_class = LaravelStylePageNumberPagination
    # The panel's student search box posts `?search=`; without these the
    # global SearchFilter matches on nothing and silently returns everyone.
    search_fields = ['user__name', 'user__phone', 'user__email']

    def get_queryset(self):
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
        payment_type = Enrollment.PaymentType.FREE

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
                Enrollment.PaymentType.FREE
                if price.amount == 0
                else Enrollment.PaymentType.PAID
            )
            if price.validity_type == CoursePrice.ValidityType.ABSOLUTE:
                valid_till = price.validity_time
            elif price.validity_duration:
                valid_till = timezone.now() + timezone.timedelta(days=price.validity_duration)

        enrollment, _ = Enrollment.objects.update_or_create(
            course=course,
            user_id=user_id,
            defaults={'valid_till': valid_till, 'payment_type': payment_type},
        )
        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)


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


    def delete(self, request):
        course = self.get_course(request.data)
        user_id = request.data.get('user_id')

        deleted = 0
        if course:
            deleted, _ = Enrollment.objects.filter(course=course, user_id=user_id).delete()
        return Response({'ok': deleted > 0})


# The legacy flat API exposed the three actions above as separate POST-only
# endpoints. These keep those paths working without duplicating the logic.


class AdminEnrollmentAttachAPIView(AdminEnrollmentAPIView):
    pass


class AdminEnrollmentUpdateAPIView(AdminEnrollmentAPIView):
    def post(self, request):
        return self.patch(request)


class AdminEnrollmentRemoveAPIView(AdminEnrollmentAPIView):
    def post(self, request):
        return self.delete(request)


class AdminEnrollmentImportAPIView(APIView):
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

            Enrollment.objects.update_or_create(
                course_id=pk,
                user=user,
                defaults={'payment_type': Enrollment.PaymentType.FREE},
            )
            attached += 1

        return Response({'attached': attached, 'missing': missing})


class AdminCourseMaterialViewSet(AdminModelViewSet):
    """Materials were list-only: the admin panel could see them and nothing
    else. There was no way to add, rename or remove one from the panel at
    all, so the screen was a dead end."""

    # `course` is rendered on every row, so without this it is a query each.
    queryset = CourseMaterial.objects.select_related('course')
    serializer_class = CourseMaterialSerializer
    search_fields = ['title', 'type', 'course__title']

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)
        # Newest first, and explicitly ordered so pagination is stable.
        return qs.order_by('-id')
