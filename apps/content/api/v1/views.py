from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.api.v1.serializers import (
    AdvertisementSerializer,
    EBookSerializer,
    HomeSerializer,
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
from apps.core.api.viewsets import (
    AdminModelViewSet,
    SlugOrPkLookupMixin,
    UnpaginatedDataListMixin,
)

# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


class PublicNoticeListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoticeSerializer
    pagination_class = LaravelStylePageNumberPagination

    def get_queryset(self):
        # `categories` is serialized on every row, so without the prefetch a
        # page of notices costs one extra query per notice.
        qs = Notice.objects.prefetch_related('categories')
        category_id = self.request.query_params.get('category_id')
        if category_id:
            qs = qs.filter(categories__id=category_id)
        return qs.distinct()


class PublicEBookListAPIView(UnpaginatedDataListMixin, ListAPIView):
    """The e-book shelf.

    The admin has managed these since the beginning (`admin/ebooks/`) and no
    public route existed, so staff could create a cover, a preview and a
    booking link that no student could ever reach. Read-only and open: an
    e-book listing is marketing, and gating it would defeat the point.
    """

    permission_classes = [AllowAny]
    serializer_class = EBookSerializer
    queryset = EBook.objects.all()


class PublicNoticeCategoryListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoticeCategorySerializer
    queryset = NoticeCategory.objects.filter(notice_category__isnull=True)


class PublicPageDetailAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary='A static CMS page by key',
        responses={200: OpenApiResponse(PageSerializer, description='`{data: {...}}`')},
    )
    def get(self, request, key):
        page = Page.objects.filter(key=key).first()
        if not page:
            raise NotFound('Page not found.')
        return Response({'data': PageSerializer(page).data})


class HomeAPIView(APIView):
    """Everything the client's landing page needs, in one round trip."""

    permission_classes = [AllowAny]

    @extend_schema(summary='Everything the landing page needs', responses={200: HomeSerializer})
    def get(self, request):
        # Imported here rather than at module scope: `courses` and `faculty`
        # both import `content`, so a top-level import back into them would
        # close the cycle.
        from apps.content.selectors import homepage_content

        return Response(
            HomeSerializer(homepage_content(), context={'request': request}).data
        )


class AdminNoticeViewSet(AdminModelViewSet):
    queryset = Notice.objects.prefetch_related('categories')
    serializer_class = NoticeSerializer
    lookup_field = 'slug'
    # Without this the global SearchFilter has nothing to match on, so
    # `?search=` was accepted and silently ignored -- the admin panel's
    # search box returned the unfiltered list and looked broken.
    search_fields = ['title', 'body']



class AdminNoticeCategoryViewSet(SlugOrPkLookupMixin, AdminModelViewSet):
    queryset = NoticeCategory.objects.all()
    serializer_class = NoticeCategorySerializer
    lookup_field = 'slug'
    search_fields = ['title']

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
    search_fields = ['name', 'designation', 'description']


class AdminAdvertisementViewSet(AdminModelViewSet):
    queryset = Advertisement.objects.all()
    serializer_class = AdvertisementSerializer
    search_fields = ['title', 'description', 'type']


class AdminEBookViewSet(AdminModelViewSet):
    queryset = EBook.objects.all()
    serializer_class = EBookSerializer
    search_fields = ['title', 'description']


class AdminPageListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = PageSerializer
    queryset = Page.objects.all()


class AdminPageUpdateAPIView(APIView):
    """Pages are seeded and only ever edited, never created or deleted."""

    permission_classes = [IsAdminRole]

    @extend_schema(summary='Edit a static page', request=PageSerializer, responses={200: PageSerializer})
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
