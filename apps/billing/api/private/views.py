"""HTTP layer for orders, payments and the admin dashboard.

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

from apps.billing import selectors, services
from apps.billing.api.serializers import (
    AdminPaymentSerializer,
    DashboardSerializer,
    PaymentChartSerializer,
    PaymentStatusUpdateRequestSerializer,
    SalesOverviewSerializer,
)
from apps.billing.models import Payment
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsFullAdmin


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
    """Confirming a payment is what actually grants course access."""

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


class AdminDashboardAPIView(APIView):
    """Headline counters for the admin panel's landing page."""

    permission_classes = [IsFullAdmin]

    @extend_schema(summary='Dashboard headline counters', responses={200: DashboardSerializer})
    def get(self, request):
        return Response(DashboardSerializer(selectors.dashboard_totals()).data)


class AdminDashboardSalesOverviewAPIView(APIView):
    """Paid-order counts per month for the last year."""

    permission_classes = [IsFullAdmin]

    @extend_schema(summary='Paid orders per month', responses={200: SalesOverviewSerializer})
    def get(self, request):
        return Response(SalesOverviewSerializer(selectors.monthly_sales()).data)


class AdminDashboardPaymentChartAPIView(APIView):
    """Paid-order income per day for the last 30 days."""

    permission_classes = [IsFullAdmin]

    @extend_schema(summary='Income per day', responses={200: PaymentChartSerializer})
    def get(self, request):
        return Response(PaymentChartSerializer(selectors.daily_income()).data)
