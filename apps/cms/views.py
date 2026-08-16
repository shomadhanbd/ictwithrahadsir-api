from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet

from .models import Advertisement, CourseMaterial, ContactMessage, EBook, Notice, NoticeCategory, Page, Testimonial
from .serializers import (
    AdvertisementSerializer,
    ContactMessageSerializer,
    CourseMaterialSerializer,
    EBookSerializer,
    HomeBannerSerializer,
    HomeCounterSerializer,
    NoticeCategorySerializer,
    NoticeSerializer,
    PageSerializer,
    TestimonialSerializer,
)

# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def public_notice_list(request):
    qs = Notice.objects.all()
    category_id = request.query_params.get("category_id")
    if category_id:
        qs = qs.filter(categories__id=category_id)
    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(qs.distinct(), request)
    return paginator.get_paginated_response(NoticeSerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_notice_category_list(request):
    qs = NoticeCategory.objects.filter(notice_category__isnull=True)
    return Response({"data": NoticeCategorySerializer(qs, many=True).data})


@api_view(["GET"])
@permission_classes([AllowAny])
def public_page_detail(request, key):
    page = Page.objects.filter(key=key).first()
    if not page:
        raise NotFound("Page not found.")
    return Response({"data": PageSerializer(page).data})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticatedOrReadOnly])
def contact_us(request):
    if request.method == "GET":
        user = request.user if request.user.is_authenticated else None
        qs = ContactMessage.objects.filter(user=user) if user else ContactMessage.objects.none()
        return Response({"data": ContactMessageSerializer(qs, many=True).data})

    serializer = ContactMessageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(user=request.user if request.user.is_authenticated else None)
    return Response(serializer.data, status=201)


@api_view(["GET"])
@permission_classes([AllowAny])
def home(request):
    from apps.courses.models import Course
    from apps.courses.serializers import CourseListSerializer
    from apps.courses.serializers import CourseCategorySerializer
    from apps.courses.models import CourseCategory
    from apps.team.models import Teacher
    from apps.team.api.v1.serializers import TeacherSerializer

    courses = Course.objects.filter(active=True, featured=True)[:12]
    categories = CourseCategory.objects.filter(category__isnull=True)
    advertisement = Advertisement.objects.all()
    testimonials = Testimonial.objects.all()
    instructors = Teacher.objects.all()
    # Homepage counters and banner are managed as `Page` rows through the
    # admin panel's Pages screen (value_type="counter"/"image"), not the
    # separate `Counter` model, which nothing in either frontend edits.
    counters_qs = Page.objects.filter(value_type=Page.ValueType.COUNTER)
    banner = Page.objects.filter(key="homeBannerImage").first()
    success_story = next(
        (c.value for c in counters_qs if c.key == "homeInstructorCounter"), 0
    )

    return Response(
        {
            "courses": CourseListSerializer(courses, many=True, context={"request": request}).data,
            "courseCategories": CourseCategorySerializer(categories, many=True).data,
            "advertisement": AdvertisementSerializer(advertisement, many=True).data,
            "testimonials": TestimonialSerializer(testimonials, many=True).data,
            "counters": HomeCounterSerializer(counters_qs, many=True).data,
            "suceesstorycounter": success_story,
            "instructors": TeacherSerializer(instructors, many=True).data,
            "bannerImage": HomeBannerSerializer(banner).data if banner else None,
        }
    )


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminNoticeViewSet(AdminModelViewSet):
    queryset = Notice.objects.all()
    serializer_class = NoticeSerializer
    lookup_field = "slug"


class AdminNoticeCategoryViewSet(AdminModelViewSet):
    queryset = NoticeCategory.objects.all()
    serializer_class = NoticeCategorySerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
        category_id = self.request.query_params.get("category_id")
        if category_id:
            qs = qs.filter(notice_category_id=category_id)
        elif self.action == "list":
            qs = qs.filter(notice_category__isnull=True)
        return qs


class AdminTestimonialViewSet(AdminModelViewSet):
    queryset = Testimonial.objects.all()
    serializer_class = TestimonialSerializer


class AdminAdvertisementViewSet(AdminModelViewSet):
    queryset = Advertisement.objects.all()
    serializer_class = AdvertisementSerializer


class AdminEBookViewSet(AdminModelViewSet):
    queryset = EBook.objects.all()
    serializer_class = EBookSerializer


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_course_materials(request):
    qs = CourseMaterial.objects.all()
    return Response({"data": CourseMaterialSerializer(qs, many=True).data})


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_contact_list(request):
    qs = ContactMessage.objects.all()
    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(ContactMessageSerializer(page, many=True).data)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_contact_toggle_read(request, pk):
    message = ContactMessage.objects.filter(pk=pk).first()
    if not message:
        raise NotFound("Message not found.")
    message.is_read = True
    message.save()
    return Response(ContactMessageSerializer(message).data)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminRole])
def admin_contact_detail(request, pk):
    message = ContactMessage.objects.filter(pk=pk).first()
    if not message:
        raise NotFound("Message not found.")
    if request.method == "DELETE":
        message.delete()
        return Response(status=204)

    reply = request.data.get("reply_message")
    if reply is None:
        raise ValidationError({"reply_message": ["This field is required."]})
    message.reply_message = reply
    message.replied_by = request.user
    message.save()
    return Response(ContactMessageSerializer(message).data)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_page_list(request):
    qs = Page.objects.all()
    return Response({"data": PageSerializer(qs, many=True).data})


@api_view(["PATCH"])
@permission_classes([IsAdminRole])
def admin_page_update(request, slug):
    page = Page.objects.filter(slug=slug).first()
    if not page:
        raise NotFound("Page not found.")
    serializer = PageSerializer(page, data=request.data, partial=True, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(PageSerializer(page).data)
