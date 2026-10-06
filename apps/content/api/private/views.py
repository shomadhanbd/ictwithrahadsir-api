from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
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
from apps.core.api.auth.permissions import IsContentStaff
from apps.core.api.views.generics import UnpaginatedDataListMixin


class AdminNoticeView:
    permission_classes = [IsContentStaff]
    queryset = Notice.objects.prefetch_related('categories')
    serializer_class = NoticeSerializer
    lookup_field = 'slug'


class AdminNoticeListCreateAPIView(AdminNoticeView, ListCreateAPIView):
    search_fields = ['title', 'body']


class AdminNoticeDetailAPIView(AdminNoticeView, RetrieveUpdateDestroyAPIView):
    pass


class AdminNoticeCategoryView:
    permission_classes = [IsContentStaff]
    queryset = NoticeCategory.objects.all()
    serializer_class = NoticeCategorySerializer


class AdminNoticeCategoryListCreateAPIView(AdminNoticeCategoryView, ListCreateAPIView):
    search_fields = ['title']

    def get_queryset(self):
        """`?category_id=` lists one category's children; without it, the top level only (the tree loads lazily)."""
        category_id = self.request.query_params.get('category_id')
        return (
            super()
            .get_queryset()
            .filter(**({'notice_category_id': category_id} if category_id else {'notice_category__isnull': True}))
        )


class AdminNoticeCategoryDetailAPIView(AdminNoticeCategoryView, RetrieveUpdateDestroyAPIView):
    pass


class AdminTestimonialView:
    permission_classes = [IsContentStaff]
    queryset = Testimonial.objects.all()
    serializer_class = TestimonialSerializer


class AdminTestimonialListCreateAPIView(AdminTestimonialView, ListCreateAPIView):
    search_fields = ['name', 'designation', 'description']


class AdminTestimonialDetailAPIView(AdminTestimonialView, RetrieveUpdateDestroyAPIView):
    pass


class AdminAdvertisementView:
    permission_classes = [IsContentStaff]
    queryset = Advertisement.objects.all()
    serializer_class = AdvertisementSerializer


class AdminAdvertisementListCreateAPIView(AdminAdvertisementView, ListCreateAPIView):
    search_fields = ['title', 'description', 'type']


class AdminAdvertisementDetailAPIView(AdminAdvertisementView, RetrieveUpdateDestroyAPIView):
    pass


class AdminEBookView:
    permission_classes = [IsContentStaff]
    queryset = EBook.objects.all()
    serializer_class = EBookSerializer


class AdminEBookListCreateAPIView(AdminEBookView, ListCreateAPIView):
    search_fields = ['title', 'description']


class AdminEBookDetailAPIView(AdminEBookView, RetrieveUpdateDestroyAPIView):
    pass


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
