"""HTTP layer for the admin billing screens: products, coupons, orders, payments.

Every handler here does the same three things and nothing else: validate the
input with a serializer, call one service or selector, render the result.
The rules themselves live in `apps/billing/services.py` (writes) and
`apps/billing/selectors.py` (reads).
"""

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import services
from apps.billing.api.serializers import (
    AdminOrderSerializer,
    AdminPaymentSerializer,
    AdminProductSerializer,
    PaymentStatusUpdateRequestSerializer,
    ProductCouponSerializer,
)
from apps.billing.models import Order, Payment, Product, ProductCoupon
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsFullAdmin
from apps.core.api.viewsets import AdminModelViewSet


class AdminProductViewSet(AdminModelViewSet):
    """Products. One somebody has paid for cannot be deleted (409); set
    `active` to false to stop selling it."""

    serializer_class = AdminProductSerializer
    queryset = Product.objects.prefetch_related('courses')
    search_fields = ['title', 'slug']
    filterset_fields = ['active']


class AdminProductCouponViewSet(AdminModelViewSet):
    serializer_class = ProductCouponSerializer
    queryset = ProductCoupon.objects.select_related('product')
    search_fields = ['code']
    filterset_fields = ['product', 'active']


class AdminOrderListAPIView(ListAPIView):
    """Every order, newest first; `?status=` narrows it."""

    permission_classes = [IsFullAdmin]
    serializer_class = AdminOrderSerializer
    pagination_class = LaravelStylePageNumberPagination
    search_fields = ['id', 'item_title', 'coupon_code', 'user__name', 'user__phone']

    def get_queryset(self):
        qs = Order.objects.select_related('user').order_by('-id')
        status_value = self.request.query_params.get('status')
        if status_value and status_value != 'all':
            qs = qs.with_status(status_value)
        return qs


class AdminPaymentListAPIView(ListAPIView):
    permission_classes = [IsFullAdmin]
    serializer_class = AdminPaymentSerializer
    pagination_class = LaravelStylePageNumberPagination
    # The panel searches by payer and by transaction reference; without these
    # the global SearchFilter had nothing to match and `?search=` was ignored.
    search_fields = ['transaction_id', 'order__user__name', 'order__user__phone']

    def get_queryset(self):
        # Newest first, and explicitly ordered: an unordered queryset lets the
        # database pick page boundaries, so a payment could show on two pages
        # or on none.
        qs = Payment.objects.with_payer().order_by('-id')

        # The screen's main job is clearing pending payments, which is
        # impossible on a mixed list once there are more than a page of them.
        status_value = self.request.query_params.get('status')
        if status_value and status_value != 'all':
            qs = qs.with_status(status_value)
        return qs


class AdminPaymentUpdateAPIView(APIView):
    """An admin's decision on a payment SSLCommerz reported but held back (a
    risk flag or a mismatch): confirm it to grant access, or fail it."""

    permission_classes = [IsFullAdmin]

    @extend_schema(
        summary='Confirm or fail a payment',
        request=PaymentStatusUpdateRequestSerializer,
        responses={200: AdminPaymentSerializer},
    )
    def patch(self, request, pk):
        payment = Payment.objects.filter(pk=pk).first()
        if not payment:
            raise NotFound('Payment not found.')

        serializer = PaymentStatusUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = services.confirm_payment(payment=payment, **serializer.validated_data)
        return Response(AdminPaymentSerializer(payment).data)
