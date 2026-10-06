from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.academic.api.public.filters import PublicBatchFilter
from apps.academic.api.public.serializers import (
    PublicBatchSerializer,
    PublicClassLevelSerializer,
    PublicGroupSerializer,
)
from apps.academic.models import Batch, ClassLevel, Group
from apps.core.api.viewsets import UnpaginatedDataListMixin


class PublicClassLevelListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicClassLevelSerializer
    queryset = ClassLevel.objects.active()


class PublicGroupListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicGroupSerializer
    queryset = Group.objects.active()


class PublicBatchListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicBatchSerializer
    queryset = Batch.objects.active().select_related("class_level")
    filterset_class = PublicBatchFilter
