import requests
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core.pagination import LaravelStylePageNumberPagination
from apps.core.permissions import IsAdminRole
from apps.core.viewsets import AdminModelViewSet

from .models import Content, Course, CourseCategory, CoursePrice, CourseUser, Coupon, Instructor, Routine, Section
from .serializers import (
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
)

# ---------------------------------------------------------------------------
# Public / client-facing
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def public_course_list(request):
    qs = Course.objects.filter(active=True)
    is_online = request.query_params.get("is_online")
    if is_online is not None:
        qs = qs.filter(is_online=is_online in ("1", "true", "True"))
    category_slug = request.query_params.get("category_slug")
    if category_slug:
        qs = qs.filter(categories__slug=category_slug)

    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(qs.distinct(), request)
    data = CourseListSerializer(page, many=True, context={"request": request}).data
    return paginator.get_paginated_response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_course_detail(request, slug):
    course = Course.objects.filter(slug=slug, active=True).first()
    if not course:
        raise NotFound("Course not found.")
    return Response(CourseDetailSerializer(course, context={"request": request}).data)


def _user_can_access_content(user, content: Content) -> bool:
    if not content.paid:
        return True
    if not user or not user.is_authenticated:
        return False
    enrollment = CourseUser.objects.filter(course_id=content.course_id, user=user).first()
    if not enrollment:
        return False
    if enrollment.valid_till and enrollment.valid_till < timezone.now():
        return False
    return True


@api_view(["GET"])
@permission_classes([AllowAny])
def content_detail(request, slug):
    content = Content.objects.filter(slug=slug, active=True).first()
    if not content:
        raise NotFound("Content not found.")
    if not _user_can_access_content(request.user, content):
        raise PermissionDenied("Not subscribed")
    return Response(ContentDetailSerializer(content, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def content_pdf(request, slug):
    content = Content.objects.filter(slug=slug, active=True).first()
    if not content or content.type != Content.Type.PDF:
        raise NotFound("PDF not found.")
    if not _user_can_access_content(request.user, content):
        raise PermissionDenied("Not subscribed")
    if not content.pdf_file:
        raise NotFound("PDF not found.")

    upstream = requests.get(content.pdf_file, stream=True, timeout=30)
    response = StreamingHttpResponse(
        upstream.iter_content(chunk_size=8192),
        content_type=upstream.headers.get("Content-Type", "application/pdf"),
    )
    response["Content-Disposition"] = f'inline; filename="{content.slug}.pdf"'
    return response


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_courses(request):
    course_ids = CourseUser.objects.filter(user=request.user).values_list("course_id", flat=True)
    qs = Course.objects.filter(id__in=course_ids, active=True)
    return Response({"data": CourseListSerializer(qs, many=True, context={"request": request}).data})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_course_category_list(request):
    qs = CourseCategory.objects.filter(category__isnull=True)
    return Response({"data": CourseCategorySerializer(qs, many=True, context={"request": request}).data})


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminCourseViewSet(AdminModelViewSet):
    queryset = Course.objects.all()
    serializer_class = AdminCourseSerializer
    lookup_field = "slug"


class AdminCourseCategoryViewSet(AdminModelViewSet):
    queryset = CourseCategory.objects.all()
    serializer_class = CourseCategorySerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        category_id = self.request.query_params.get("category_id")
        if category_id:
            qs = qs.filter(category_id=category_id)
        elif self.action == "list":
            qs = qs.filter(category__isnull=True)
        return qs


class AdminInstructorViewSet(AdminModelViewSet):
    queryset = Instructor.objects.all()
    serializer_class = InstructorSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get("course_id")
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminCoursePriceViewSet(AdminModelViewSet):
    queryset = CoursePrice.objects.all()
    serializer_class = CoursePriceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        priceable_type = self.request.query_params.get("priceable_type")
        if priceable_type:
            qs = qs.filter(priceable_type=priceable_type)
        # The admin panel filters a course's prices with `?priceable_type=course&course_id=<id>`
        # -- course_id here means "the priceable_id when priceable_type is course".
        course_id = self.request.query_params.get("course_id")
        if course_id:
            qs = qs.filter(priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=course_id)
        return qs


class AdminCouponViewSet(AdminModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        price_id = self.request.query_params.get("price_id")
        if price_id:
            qs = qs.filter(price_id=price_id)
        return qs


class AdminRoutineViewSet(AdminModelViewSet):
    queryset = Routine.objects.all()
    serializer_class = RoutineSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get("course_id")
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs


class AdminSectionViewSet(AdminModelViewSet):
    queryset = Section.objects.all()
    serializer_class = AdminSectionSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        course_id = self.request.query_params.get("course_id")
        section_id = self.request.query_params.get("section_id")
        if course_id:
            qs = qs.filter(course_id=course_id)
        if section_id:
            qs = qs.filter(section_id=section_id)
        elif course_id and self.action == "list":
            qs = qs.filter(section__isnull=True)
        return qs


class AdminContentViewSet(AdminModelViewSet):
    queryset = Content.objects.all()
    serializer_class = AdminContentSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        section_id = self.request.query_params.get("section_id")
        if section_id:
            qs = qs.filter(section_id=section_id)
        return qs


@api_view(["GET"])
@permission_classes([IsAdminRole])
def toggle_content(request, pk):
    content = Content.objects.filter(pk=pk).first()
    if not content:
        raise NotFound("Content not found.")
    action = request.query_params.get("action")
    if action == "active":
        content.active = not content.active
    elif action == "paid":
        content.paid = not content.paid
    else:
        raise ValidationError({"action": ["Must be `active` or `paid`."]})
    content.save()
    return Response(AdminContentSerializer(content).data)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def course_enrolled_users(request, pk):
    qs = CourseUser.objects.filter(course_id=pk).select_related("user")
    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(CourseUserSerializer(page, many=True).data)


def _resolve_course_from_slug_or_id(value):
    """The admin panel identifies a course by `slugOrId` on the enrollment
    endpoints -- either the numeric id or the slug, never `course_id`."""
    if value is None:
        return None
    value = str(value)
    if value.isdigit():
        return Course.objects.filter(pk=int(value)).first()
    return Course.objects.filter(slug=value).first()


def _course_from_request(data):
    return _resolve_course_from_slug_or_id(
        data.get("slugOrId") or data.get("course_id")
    )


@api_view(["POST"])
@permission_classes([IsAdminRole])
def course_user_attach(request):
    course = _course_from_request(request.data)
    user_id = request.data.get("user_id")
    price_id = request.data.get("price_id")
    if not course or not user_id:
        raise ValidationError({"user_id": ["A valid course and user_id are required."]})

    # The admin UI only sends `price_id` on attach -- validity and payment
    # type are derived from that price's own rule, not supplied by the caller.
    valid_till = None
    payment_type = CourseUser.PaymentType.FREE
    if price_id:
        price = CoursePrice.objects.filter(
            pk=price_id, priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=course.id
        ).first()
        if not price:
            raise ValidationError({"price_id": ["This price does not belong to the selected course."]})
        payment_type = (
            CourseUser.PaymentType.FREE if price.amount == 0 else CourseUser.PaymentType.PAID
        )
        if price.validity_type == CoursePrice.ValidityType.ABSOLUTE:
            valid_till = price.validity_time
        elif price.validity_duration:
            valid_till = timezone.now() + timezone.timedelta(days=price.validity_duration)

    enrollment, _ = CourseUser.objects.update_or_create(
        course=course,
        user_id=user_id,
        defaults={"valid_till": valid_till, "payment_type": payment_type},
    )
    return Response(CourseUserSerializer(enrollment).data, status=201)


@api_view(["POST"])
@permission_classes([IsAdminRole])
def course_user_update(request):
    course = _course_from_request(request.data)
    user_id = request.data.get("user_id")
    enrollment = (
        CourseUser.objects.filter(course=course, user_id=user_id).first() if course else None
    )
    if not enrollment:
        raise NotFound("Enrollment not found.")
    if "valid_till" in request.data:
        enrollment.valid_till = request.data.get("valid_till") or None
    if "payment_type" in request.data:
        enrollment.payment_type = request.data.get("payment_type")
    enrollment.save()
    return Response(CourseUserSerializer(enrollment).data)


@api_view(["POST"])
@permission_classes([IsAdminRole])
def course_user_remove(request):
    course = _course_from_request(request.data)
    user_id = request.data.get("user_id")
    deleted = 0
    if course:
        deleted, _ = CourseUser.objects.filter(course=course, user_id=user_id).delete()
    return Response({"ok": deleted > 0})


@api_view(["POST"])
@permission_classes([IsAdminRole])
def course_user_import(request, pk):
    file = request.FILES.get("file")
    if not file:
        raise ValidationError({"file": ["An Excel file is required."]})

    import openpyxl

    workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c).strip().lower() if c else "" for c in rows[0]] if rows else []
    attached, missing = 0, 0
    for row in rows[1:]:
        record = dict(zip(header, row))
        phone = str(record.get("phone") or "").strip()
        user = User.objects.filter(phone=phone).first() if phone else None
        if not user:
            missing += 1
            continue
        CourseUser.objects.update_or_create(
            course_id=pk, user=user, defaults={"payment_type": CourseUser.PaymentType.FREE}
        )
        attached += 1

    return Response({"attached": attached, "missing": missing})
