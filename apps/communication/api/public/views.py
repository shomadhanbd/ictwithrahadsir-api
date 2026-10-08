from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.api.filters import NoticeFilter
from apps.communication.api.serializers import NoticeCategorySerializer, NoticeSerializer
from apps.communication.models import NoticeCategory
from apps.communication.selectors import notice_board, unread_notice_count
from apps.communication.services import mark_notices_seen
from apps.core.api.views.generics import UnpaginatedDataListMixin


class PublicNoticeListAPIView(ListAPIView):
    """`?category_id=`."""

    permission_classes = [AllowAny]
    serializer_class = NoticeSerializer
    filterset_class = NoticeFilter

    def get_queryset(self):
        return notice_board(self.request.user)


class PublicNoticeCategoryListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NoticeCategorySerializer
    queryset = NoticeCategory.objects.all()


class MyUnreadNoticesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"count": unread_notice_count(request.user)})


class MyNoticesSeenAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"seen_at": mark_notices_seen(request.user).seen_at})
