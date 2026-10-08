from rest_framework import status
from rest_framework.generics import (
    CreateAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    UpdateAPIView,
)
from rest_framework.response import Response

from apps.core.api.auth.permissions import IsContentStaff, IsFullAdmin
from apps.core.api.views.generics import SerializerAPIView, UnpaginatedDataListMixin
from apps.materials.api.serializers import (
    AdminBookOrderSerializer,
    AdminCategorySerializer,
    AdminItemSerializer,
    AdminTopicDetailSerializer,
    AdminTopicSerializer,
    DeliveryRateSerializer,
    MoveSerializer,
)
from apps.materials.models import DeliveryRate, MaterialItem
from apps.materials.selectors import admin_categories, admin_topics, paid_book_orders
from apps.materials.services import move_item, next_item_order


class AdminCategoryMixin:
    permission_classes = [IsContentStaff]
    serializer_class = AdminCategorySerializer

    def get_queryset(self):
        return admin_categories()


class AdminCategoryListCreateAPIView(AdminCategoryMixin, UnpaginatedDataListMixin, ListCreateAPIView):
    pass


class AdminCategoryDetailAPIView(AdminCategoryMixin, RetrieveUpdateDestroyAPIView):
    pass


class AdminTopicListCreateAPIView(ListCreateAPIView):
    """`?category=<id>&search=`."""

    permission_classes = [IsContentStaff]
    serializer_class = AdminTopicSerializer
    filterset_fields = ["category"]
    search_fields = ["title", "description"]

    def get_queryset(self):
        return admin_topics()


class AdminTopicDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsContentStaff]
    serializer_class = AdminTopicDetailSerializer

    def get_queryset(self):
        return admin_topics().prefetch_related("items")


class AdminItemCreateAPIView(CreateAPIView):
    permission_classes = [IsContentStaff]
    serializer_class = AdminItemSerializer

    def perform_create(self, serializer):
        serializer.save(order=next_item_order(serializer.validated_data["topic"]))


class AdminItemDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsContentStaff]
    serializer_class = AdminItemSerializer
    queryset = MaterialItem.objects.all()


class AdminItemMoveAPIView(SerializerAPIView):
    permission_classes = [IsContentStaff]
    serializer_class = MoveSerializer
    queryset = MaterialItem.objects.all()

    def post(self, request, pk):
        move_item(self.get_object(), **self.validated_data(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminBookOrderListAPIView(ListAPIView):
    """`?search=` a name, phone, book or transaction ID."""

    permission_classes = [IsFullAdmin]
    serializer_class = AdminBookOrderSerializer
    search_fields = ["name", "phone", "title", "payment__transaction_id"]

    def get_queryset(self):
        return paid_book_orders()


class AdminDeliveryRateListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [IsFullAdmin]
    serializer_class = DeliveryRateSerializer
    queryset = DeliveryRate.objects.all()


class AdminDeliveryRateDetailAPIView(UpdateAPIView):
    permission_classes = [IsFullAdmin]
    serializer_class = DeliveryRateSerializer
    queryset = DeliveryRate.objects.all()
    lookup_field = "zone"
