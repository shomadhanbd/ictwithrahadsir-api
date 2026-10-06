from django.http import HttpResponseRedirect

from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.api.filters import PublicProductFilter
from apps.billing.api.serializers import (
    PaymentInitiateRequestSerializer,
    PaymentInitiateResponseSerializer,
    PaymentSerializer,
    ProductSerializer,
)
from apps.billing.models import Payment, Product
from apps.billing.services import (
    initiate_payment,
    process_capture,
    process_ipn,
)
from apps.core.api.viewsets import UnpaginatedDataListMixin


class ProductListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    queryset = Product.objects.on_sale().prefetch_related("courses")
    search_fields = ["title", "description"]
    filterset_class = PublicProductFilter


class PaymentInitiateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PaymentInitiateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = initiate_payment(
            user=request.user,
            product_id=serializer.validated_data["product_id"],
        )
        return Response(PaymentInitiateResponseSerializer(result).data, status=status.HTTP_201_CREATED)


class PaymentCaptureView(APIView):
    """No auth: the payload is signature-checked and a VALID is confirmed with the Validator API."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        result = process_capture(request.data)
        return HttpResponseRedirect(result["redirect_url"])


class PaymentIPNView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        process_ipn(request.data)
        return Response(status=status.HTTP_200_OK)


class MyPaymentListView(UnpaginatedDataListMixin, ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        return (
            Payment.objects.filter(user=self.request.user)
            .select_related("product")
            .prefetch_related("product__courses")
        )


class MyPaymentDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    lookup_field = "transaction_id"
    lookup_url_kwarg = "tran_id"

    def get_queryset(self):
        return (
            Payment.objects.filter(user=self.request.user)
            .select_related("product")
            .prefetch_related("product__courses")
        )
