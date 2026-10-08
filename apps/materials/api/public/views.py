from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.billing.api.serializers import PaymentInitiateResponseSerializer
from apps.core.api.views.generics import SerializerAPIView, UnpaginatedDataListMixin
from apps.materials.api.serializers import BookOrderRequestSerializer, DeliveryRateSerializer, LibraryTopicSerializer
from apps.materials.models import DeliveryRate
from apps.materials.selectors import library_topics, opens_for
from apps.materials.services import order_book


class MaterialLibraryAPIView(UnpaginatedDataListMixin, ListAPIView):
    """`?class_level=<slug>`."""

    permission_classes = [AllowAny]
    serializer_class = LibraryTopicSerializer

    def get_queryset(self):
        return library_topics(class_level=self.request.query_params.get("class_level"))

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "opens": opens_for(self.request.user)}


class DeliveryRateListAPIView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DeliveryRateSerializer
    queryset = DeliveryRate.objects.all()


class BookOrderAPIView(SerializerAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookOrderRequestSerializer

    def post(self, request):
        result = order_book(user=request.user, **self.validated_data(request))
        return Response(PaymentInitiateResponseSerializer(result).data, status=status.HTTP_201_CREATED)
