from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.api.serializers import (
    HomeSerializer,
    PageSerializer,
)
from apps.content.models import (
    Page,
)


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
