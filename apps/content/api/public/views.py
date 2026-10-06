from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.api.serializers import (
    EBookSerializer,
    HomeSerializer,
    NoticeCategorySerializer,
    NoticeSerializer,
    PageSerializer,
)
from apps.content.models import (
    EBook,
    Notice,
    NoticeCategory,
    Page,
)
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.viewsets import (
    UnpaginatedDataListMixin,
)


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
            if not category_id.isdigit():
                raise ValidationError({'category_id': ['Must be a category id.']})
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

    def get(self, request, key):
        page = Page.objects.filter(key=key).first()
        if not page:
            raise NotFound('Page not found.')
        return Response({'data': PageSerializer(page).data})


class HomeAPIView(APIView):
    """Everything the client's landing page needs, in one round trip."""

    permission_classes = [AllowAny]

    def get(self, request):
        # Imported here rather than at module scope: `courses` imports
        # `content`, so a top-level import back into it would close the cycle.
        from apps.content.selectors import homepage_content

        return Response(HomeSerializer(homepage_content(request.user), context={'request': request}).data)
