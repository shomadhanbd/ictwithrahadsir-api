from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.auth.permissions import IsContentStaff
from apps.core.api.views.generics import SerializerAPIView, UnpaginatedDataListMixin
from apps.website.api.serializers import (
    AdminBannerSerializer,
    AdminSectionSerializer,
    MoveSerializer,
    SectionUpdateSerializer,
)
from apps.website.models import Banner
from apps.website.registry import PAGES, REGISTRY
from apps.website.selectors import section_state, section_states
from apps.website.services import move_banner, next_banner_order, reset_section, update_section


class AdminSectionListAPIView(APIView):
    """`{pages, data}`: the website's pages and every section with its form and content."""

    permission_classes = [IsContentStaff]

    def get(self, request):
        return Response(
            {
                "pages": [{"key": key, "label": label} for key, label in PAGES],
                "data": AdminSectionSerializer(section_states(), many=True).data,
            }
        )


class AdminSectionDetailAPIView(SerializerAPIView):
    """PATCH `{content?, is_visible?}`; DELETE puts the section back to its original copy."""

    permission_classes = [IsContentStaff]
    serializer_class = SectionUpdateSerializer

    def get_key(self) -> str:
        key = self.kwargs["key"]
        if key not in REGISTRY:
            raise NotFound("Unknown section.")
        return key

    def respond(self, key):
        return Response(AdminSectionSerializer(section_state(key)).data)

    def get(self, request, key):
        return self.respond(self.get_key())

    def patch(self, request, key):
        key = self.get_key()
        update_section(key, **self.validated_data(request))
        return self.respond(key)

    def delete(self, request, key):
        key = self.get_key()
        reset_section(key)
        return self.respond(key)


class AdminBannerMixin:
    permission_classes = [IsContentStaff]
    serializer_class = AdminBannerSerializer
    queryset = Banner.objects.all()


class AdminBannerListCreateAPIView(AdminBannerMixin, UnpaginatedDataListMixin, ListCreateAPIView):
    def perform_create(self, serializer):
        serializer.save(order=next_banner_order())


class AdminBannerDetailAPIView(AdminBannerMixin, RetrieveUpdateDestroyAPIView):
    pass


class AdminBannerMoveAPIView(SerializerAPIView):
    """POST `{direction: "up" | "down"}`."""

    permission_classes = [IsContentStaff]
    serializer_class = MoveSerializer
    queryset = Banner.objects.all()

    def post(self, request, pk):
        move_banner(self.get_object(), **self.validated_data(request))
        return Response(status=status.HTTP_204_NO_CONTENT)
