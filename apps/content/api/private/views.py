from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.api.serializers import (
    AdvertisementSerializer,
    EBookSerializer,
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
from apps.core.api.permissions import IsContentStaff
from apps.core.api.viewsets import (
    AdminModelViewSet,
    SlugOrPkLookupMixin,
    UnpaginatedDataListMixin,
)


class AdminNoticeViewSet(AdminModelViewSet):
    permission_classes = [IsContentStaff]
    queryset = Notice.objects.prefetch_related('categories')
    serializer_class = NoticeSerializer
    lookup_field = 'slug'
    # Without this the global SearchFilter has nothing to match on, so
    # `?search=` was accepted and silently ignored -- the admin panel's
    # search box returned the unfiltered list and looked broken.
    search_fields = ['title', 'body']


class AdminNoticeCategoryViewSet(SlugOrPkLookupMixin, AdminModelViewSet):
    permission_classes = [IsContentStaff]
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
    permission_classes = [IsContentStaff]
    queryset = Testimonial.objects.all()
    serializer_class = TestimonialSerializer
    search_fields = ['name', 'designation', 'description']


class AdminAdvertisementViewSet(AdminModelViewSet):
    permission_classes = [IsContentStaff]
    queryset = Advertisement.objects.all()
    serializer_class = AdvertisementSerializer
    search_fields = ['title', 'description', 'type']


class AdminEBookViewSet(AdminModelViewSet):
    permission_classes = [IsContentStaff]
    queryset = EBook.objects.all()
    serializer_class = EBookSerializer
    search_fields = ['title', 'description']


class AdminPageListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [IsContentStaff]
    serializer_class = PageSerializer
    queryset = Page.objects.all()


class AdminPageUpdateAPIView(APIView):
    """Pages are seeded and only ever edited, never created or deleted."""

    permission_classes = [IsContentStaff]

    def patch(self, request, slug):
        page = Page.objects.filter(slug=slug).first()
        if not page:
            raise NotFound('Page not found.')

        serializer = PageSerializer(page, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PageSerializer(page).data)
