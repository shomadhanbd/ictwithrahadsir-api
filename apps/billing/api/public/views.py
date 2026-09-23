"""HTTP layer for orders and payments.

Every handler here does the same three things and nothing else: validate the
input with a serializer, call one service or selector, render the result.
The rules themselves live in `apps/billing/services.py` (writes) and
`apps/billing/selectors.py` (reads).
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import services
from apps.billing.api.serializers import (
    FreeEnrollmentRequestSerializer,
    FreeEnrollmentResponseSerializer,
    OrderCreateRequestSerializer,
    OrderCreateResponseSerializer,
    OrderSerializer,
    PaymentSerializer,
    PaymentSubmitRequestSerializer,
)
from apps.billing.models import Order
from apps.courses.models import Course


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

        course = Course.objects.filter(pk=serializer.validated_data['course_id'], active=True).first()
        if not course:
            raise NotFound('Course not found.')

        services.claim_free_course(user=request.user, course=course)
        return Response(FreeEnrollmentResponseSerializer({'ok': True, 'course_id': course.id}).data)


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
        summary='Place an order for a course',
        request=OrderCreateRequestSerializer,
        responses={201: OrderCreateResponseSerializer},
    )
    def post(self, request):
        serializer = OrderCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.create_course_order(user=request.user, **serializer.validated_data)

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
