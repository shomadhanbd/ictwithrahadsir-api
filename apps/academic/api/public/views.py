from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.academic import selectors
from apps.academic.api.public.filters import PublicBatchFilter
from apps.academic.api.public.serializers import (
    PublicBatchSerializer,
    PublicClassLevelSerializer,
    PublicGroupSerializer,
)
from apps.core.api.views.generics import UnpaginatedDataListMixin


class PublicClassLevelListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicClassLevelSerializer

    def get_queryset(self):
        return selectors.active_class_levels()


class PublicGroupListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicGroupSerializer

    def get_queryset(self):
        return selectors.active_groups()


class PublicBatchListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicBatchSerializer

    def get_queryset(self):
        return selectors.active_batches()

    filterset_class = PublicBatchFilter
