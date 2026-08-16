from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.api.v1.serializers import (
    AdvertisementSerializer,
    EBookSerializer,
    HomeBannerSerializer,
    HomeCounterSerializer,
    NoticeCategorySerializer,
    NoticeSerializer,
    PageSerializer,
    TestimonialSerializer,
)
from apps.content.models import (
    Advertisement,
    EBook,
    Notice,
    NoticeCategory,
    Page,
    Testimonial,
)
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet

# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


class PublicNoticeListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoticeSerializer
    pagination_class = LaravelStylePageNumberPagination

    def get_queryset(self):
        qs = Notice.objects.all()
        category_id = self.request.query_params.get('category_id')
        if category_id:
            qs = qs.filter(categories__id=category_id)
        return qs.distinct()


class PublicNoticeCategoryListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoticeCategorySerializer
    pagination_class = None
    queryset = NoticeCategory.objects.filter(notice_category__isnull=True)

    def list(self, request, *args, **kwargs):
        return Response({'data': self.get_serializer(self.get_queryset(), many=True).data})


class PublicPageDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, key):
        page = Page.objects.filter(key=key).first()
        if not page:
            raise NotFound('Page not found.')
        return Response({'data': PageSerializer(page).data})


class HomeAPIView(APIView):
    """Everything the client's landing page needs, in one round trip."""

    permission_classes = [AllowAny]

    def get(self, request):
        # Imported lazily: courses and team both reach back into cms, so
        # importing at module scope would create a cycle.
        from apps.courses.api.v1.serializers import (
            CourseCategorySerializer,
            CourseListSerializer,
            build_course_stats,
        )
        from apps.courses.models import Course, CourseCategory
        from apps.faculty.api.v1.serializers import TeacherSerializer
        from apps.faculty.models import Teacher

        courses = list(
            Course.objects.filter(active=True, featured=True)
            .prefetch_related('categories', 'instructors', 'routines')[:12]
        )
        categories = CourseCategory.objects.filter(category__isnull=True)

        # Homepage counters and banner are managed as `Page` rows through the
        # admin panel's Pages screen (value_type="counter"/"image"), not the
        # separate `Counter` model, which nothing in either frontend edits.
        counters = Page.objects.filter(value_type=Page.ValueType.COUNTER)
        banner = Page.objects.filter(key='homeBannerImage').first()
        success_story = next(
            (c.value for c in counters if c.key == 'homeInstructorCounter'), 0
        )

        return Response(
            {
                'courses': CourseListSerializer(
                    courses,
                    many=True,
                    context={
                        'request': request,
                        'course_stats': build_course_stats(courses, request),
                    },
                ).data,
                'courseCategories': CourseCategorySerializer(categories, many=True).data,
                'advertisement': AdvertisementSerializer(
                    Advertisement.objects.all(), many=True
                ).data,
                'testimonials': TestimonialSerializer(
                    Testimonial.objects.all(), many=True
                ).data,
                'counters': HomeCounterSerializer(counters, many=True).data,
                'suceesstorycounter': success_story,
                'instructors': TeacherSerializer(Teacher.objects.all(), many=True).data,
                'bannerImage': HomeBannerSerializer(banner).data if banner else None,
            }
        )


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminNoticeViewSet(AdminModelViewSet):
    queryset = Notice.objects.all()
    serializer_class = NoticeSerializer
    lookup_field = 'slug'


class AdminNoticeCategoryViewSet(AdminModelViewSet):
    queryset = NoticeCategory.objects.all()
    serializer_class = NoticeCategorySerializer
    lookup_field = 'slug'

    def get_queryset(self):
        qs = super().get_queryset()
        category_id = self.request.query_params.get('category_id')
        if category_id:
            return qs.filter(notice_category_id=category_id)
        if self.action == 'list':
            # Top level only, so the admin panel can expand the tree lazily.
            return qs.filter(notice_category__isnull=True)
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


class AdminPageListAPIView(ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = PageSerializer
    pagination_class = None
    queryset = Page.objects.all()

    def list(self, request, *args, **kwargs):
        return Response({'data': self.get_serializer(self.get_queryset(), many=True).data})


class AdminPageUpdateAPIView(APIView):
    """Pages are seeded and only ever edited, never created or deleted."""

    permission_classes = [IsAdminRole]

    def patch(self, request, slug):
        page = Page.objects.filter(slug=slug).first()
        if not page:
            raise NotFound('Page not found.')

        serializer = PageSerializer(
            page, data=request.data, partial=True, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PageSerializer(page).data)
