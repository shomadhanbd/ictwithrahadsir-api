from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
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
)
from apps.core.spreadsheets import read_records
from apps.courses.api.base import (
    BaseCourseEnrollmentAPIView,
)
from apps.courses.api.filters import (
    ContentFilter,
    CouponFilter,
    CourseMaterialFilter,
    CoursePriceFilter,
    CourseTeacherFilter,
    RoutineFilter,
    SectionFilter,
)
from apps.courses.api.serializers import (
    AdminContentSerializer,
    AdminCourseSerializer,
    AdminCourseTeacherSerializer,
    AdminEnrollmentRequestSerializer,
    AdminSectionSerializer,
    CouponSerializer,
    CourseCategorySerializer,
    CourseMaterialSerializer,
    CoursePriceSerializer,
    EnrollmentImportRequestSerializer,
    EnrollmentSerializer,
    RoutineSerializer,
)
from apps.courses.models import (
    Content,
    Coupon,
    Course,
    CourseCategory,
    CourseMaterial,
    CoursePrice,
    CourseTeacher,
    Enrollment,
    Routine,
    Section,
)
from apps.courses.services import (
    grant_from_price,
    import_enrollments,
    revoke_course_access,
)
from apps.identity.models import User


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
    queryset = Content.objects.all()
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
            # `user.role` reads group membership, so without this every row
            # on the page costs its own query to serialize.
            .prefetch_related('user__groups')
            .order_by('-id')
        )


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
                raise ValidationError({'price_id': ['This price does not belong to the selected course.']})

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
        enrollment = Enrollment.objects.filter(course=course, user_id=user_id).first() if course else None
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


class AdminCourseTeacherViewSet(AdminModelViewSet):
    """The teachers assigned to one course, with their commission.

    `IsFullAdmin` rather than `IsCourseTeacher`: who teaches a course and
    on what commission is not a teacher's own business to edit.
    """

    permission_classes = [IsFullAdmin]
    queryset = CourseTeacher.objects.select_related('user__teacher', 'course')
    serializer_class = AdminCourseTeacherSerializer
    # Everything shown in the panel's table lives on the account or the roster
    # now, so every search field crosses a join.
    search_fields = [
        'user__name',
        'user__email',
        'user__teacher__designation',
        'user__teacher__institute',
    ]
    filterset_class = CourseTeacherFilter
