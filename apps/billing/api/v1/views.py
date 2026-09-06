"""HTTP layer for orders, payments and the admin dashboard.

Every handler here does the same three things and nothing else: validate the
input with a serializer, call one service or selector, render the result.
The rules themselves live in `apps/billing/services.py` (writes) and
`apps/billing/selectors.py` (reads).
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import selectors, services
from apps.billing.api.v1.serializers import (
    AdminPaymentSerializer,
    DashboardSerializer,
    FreeEnrollmentRequestSerializer,
    FreeEnrollmentResponseSerializer,
    OrderCreateRequestSerializer,
    OrderCreateResponseSerializer,
    OrderSerializer,
    PaymentChartSerializer,
    PaymentSerializer,
    PaymentStatusUpdateRequestSerializer,
    PaymentSubmitRequestSerializer,
    SalesOverviewSerializer,
)
from apps.billing.models import Order, Payment
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsFullAdmin
from apps.courses.models import Course

# ---------------------------------------------------------------------------
# Purchases / orders / payments
# ---------------------------------------------------------------------------


class FreeEnrollmentAPIView(APIView):
    """Self-enrolment on a course that has a zero-cost price.

    Named for what it creates. The legacy path called it
    `free-course-purchase`, though nothing is purchased.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Claim a free course',
        request=FreeEnrollmentRequestSerializer,
        responses={200: FreeEnrollmentResponseSerializer},
    )
    def post(self, request):
        serializer = FreeEnrollmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        course = Course.objects.filter(
            pk=serializer.validated_data['course_id'], active=True
        ).first()
        if not course:
            raise NotFound('Course not found.')

        services.claim_free_course(user=request.user, course=course)
        return Response(
            FreeEnrollmentResponseSerializer({'ok': True, 'course_id': course.id}).data
        )


class OrderAPIView(APIView):
    """GET lists the caller's orders, POST places one.

    The legacy API split these across a singular `order` and a plural
    `orders`, which read as two different resources.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List the caller's orders",
        responses={200: OpenApiResponse(OrderSerializer(many=True), description='`{data: [...]}`')},
    )
    def get(self, request):
        orders = Order.objects.for_user(request.user)
        return Response({'data': OrderSerializer(orders, many=True).data})

    @extend_schema(
        summary='Place an order for a course or a product',
        request=OrderCreateRequestSerializer,
        responses={201: OrderCreateResponseSerializer},
    )
    def post(self, request):
        serializer = OrderCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        selection = serializer.validated_data

        if 'product' in selection:
            order = services.create_product_order(user=request.user, **selection)
        else:
            order = services.create_course_order(user=request.user, **selection)

        return Response(
            OrderCreateResponseSerializer({'id': order.id, 'order': order}).data,
            status=status.HTTP_201_CREATED,
        )


class PaymentSubmitAPIView(APIView):
    """Records a manual mobile-banking transfer against an order. An admin
    confirms it later; nothing here marks the order paid."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Submit a manual mobile-banking transfer',
        request=PaymentSubmitRequestSerializer,
        responses={201: PaymentSerializer},
    )
    def post(self, request):
        serializer = PaymentSubmitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = Order.objects.filter(pk=data['order_id'], user=request.user).first()
        if not order:
            raise NotFound('Order not found.')

        payment = services.submit_payment(
            order=order,
            transaction_id=data['transaction_id'],
            details=data['details'],
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Admin dashboard
#
# Lives here because three of its four payloads are order and revenue
# aggregates. It also counts courses and students, but billing already
# depends on both of those apps for Order.course and Order.user, so this
# adds no new dependency edge.
# ---------------------------------------------------------------------------


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
