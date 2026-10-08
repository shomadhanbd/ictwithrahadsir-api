from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.website.api.serializers import HomeSerializer
from apps.website.registry import REGISTRY, legal_key
from apps.website.selectors import home_content, section_state, site_payload


class WebsiteAPIView(APIView):
    """Every shown section's content by key (policy pages aside); shared by all website pages."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(site_payload())


class HomeAPIView(APIView):
    """The home page's courses, banners, featured feedback, numbers and teachers."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(HomeSerializer(home_content(request.user), context={"request": request}).data)


class LegalPageAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        key = legal_key(slug)
        if key not in REGISTRY:
            raise NotFound("Page not found.")
        return Response(section_state(key).content)
