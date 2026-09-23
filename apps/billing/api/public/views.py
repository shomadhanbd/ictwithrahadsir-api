"""HTTP layer for products, orders and SSLCommerz payments.

Every handler here does the same three things and nothing else: validate the
input with a serializer, call one service or selector, render the result.
The rules themselves live in `apps/billing/services.py` (writes) and
`apps/billing/selectors.py` (reads).
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import selectors, services, sslcommerz
from apps.billing.api.serializers import (
    FreeEnrollmentRequestSerializer,
    FreeEnrollmentResponseSerializer,
    OrderCreateRequestSerializer,
    OrderCreateResponseSerializer,
    OrderPayResponseSerializer,
    OrderQuoteSerializer,
    OrderSerializer,
    ProductSerializer,
    SslCommerzCallbackSerializer,
)
from apps.billing.models import Order, Payment, Product
from apps.core.api.responses import OkResponseSerializer
from apps.core.api.viewsets import SlugOrPkLookupMixin, UnpaginatedDataListMixin
from apps.courses.models import Course

logger = logging.getLogger('payments')


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


# -- products ------------------------------------------------------------------


class ProductListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(active=True).prefetch_related('courses')
    search_fields = ['title', 'description']


class ProductDetailAPIView(SlugOrPkLookupMixin, RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(active=True).prefetch_related('courses')
    lookup_field = 'slug'


class MyProductListAPIView(UnpaginatedDataListMixin, ListAPIView):
    """The products the caller has paid for. The courses they unlock are in
    `me/courses/` like any other enrolment."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer
    queryset = Product.objects.none()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Product.objects.none()
        return selectors.owned_products(self.request.user)


# -- orders --------------------------------------------------------------------


class OrderAPIView(APIView):
    """GET lists the caller's orders, POST places one."""

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
        order = services.create_order(user=request.user, **serializer.validated_data)

        return Response(
            OrderCreateResponseSerializer({'id': order.id, 'order': order}).data,
            status=status.HTTP_201_CREATED,
        )


class OrderQuoteAPIView(APIView):
    """What an order would cost with a coupon. Places nothing."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Price an order, e.g. to check a coupon',
        request=OrderCreateRequestSerializer,
        responses={200: OrderQuoteSerializer},
    )
    def post(self, request):
        serializer = OrderCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quote = services.quote(user=request.user, **serializer.validated_data)
        return Response(OrderQuoteSerializer(quote).data)


class OrderPayAPIView(APIView):
    """Start paying for one of the caller's orders through SSLCommerz."""

    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Pay for an order', request=None, responses={200: OrderPayResponseSerializer})
    def post(self, request, pk):
        order = Order.objects.filter(pk=pk, user=request.user).first()
        if order is None:
            raise NotFound('Order not found.')

        gateway_url = services.start_payment(order=order)
        order.refresh_from_db()
        return Response(OrderPayResponseSerializer({'gateway_url': gateway_url, 'order': order}).data)


# -- SSLCommerz callbacks --------------------------------------------------------
#
# SSLCommerz posts these, from the student's browser (success/fail/cancel) or
# from its own servers (IPN). They carry no token, so they take no auth; they
# are safe because nothing they post is trusted -- a payment is only ever
# settled from what the validation API says about its unguessable `tran_id`.


def _result_redirect(order_id, result):
    """Back to the frontend. The target is a setting, never taken from input."""
    query = urlencode({'order_id': order_id or '', 'status': result})
    return HttpResponseRedirect(f'{settings.PAYMENT_RESULT_URL}?{query}')


def _payment_order_id(tran_id):
    return Payment.objects.filter(transaction_id=tran_id).values_list('order_id', flat=True).first()


class SslCommerzCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def callback_data(self, request):
        serializer = SslCommerzCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class SslCommerzSuccessView(SslCommerzCallbackView):
    @extend_schema(summary='SSLCommerz success callback', request=SslCommerzCallbackSerializer, responses={302: None})
    def post(self, request):
        data = self.callback_data(request)
        order_id = _payment_order_id(data['tran_id'])
        if order_id is None or not data['val_id']:
            return _result_redirect(order_id, 'failed')
        try:
            payment = services.complete_payment(tran_id=data['tran_id'], val_id=data['val_id'])
        except sslcommerz.SslCommerzError:
            # The IPN will settle it; tell the student it is being confirmed.
            return _result_redirect(order_id, 'pending')

        result = {Payment.Status.SUCCESSFUL: 'paid', Payment.Status.PENDING: 'pending'}.get(payment.status, 'failed')
        return _result_redirect(order_id, result)


class SslCommerzFailView(SslCommerzCallbackView):
    cancelled = False

    @extend_schema(summary='SSLCommerz fail callback', request=SslCommerzCallbackSerializer, responses={302: None})
    def post(self, request):
        data = self.callback_data(request)
        order_id = _payment_order_id(data['tran_id'])
        if order_id is not None:
            services.fail_payment(tran_id=data['tran_id'], cancelled=self.cancelled)
        return _result_redirect(order_id, 'cancelled' if self.cancelled else 'failed')


class SslCommerzCancelView(SslCommerzFailView):
    cancelled = True

    @extend_schema(summary='SSLCommerz cancel callback', request=SslCommerzCallbackSerializer, responses={302: None})
    def post(self, request):
        return super().post(request)


class SslCommerzIpnView(SslCommerzCallbackView):
    """SSLCommerz's server-to-server notice. Register this URL as the IPN URL."""

    @extend_schema(
        summary='SSLCommerz IPN',
        request=SslCommerzCallbackSerializer,
        responses={200: OkResponseSerializer},
    )
    def post(self, request):
        data = self.callback_data(request)
        if _payment_order_id(data['tran_id']) is None:
            raise NotFound('Unknown transaction.')

        if data['status'] in sslcommerz.PAID_STATUSES and data['val_id']:
            services.complete_payment(tran_id=data['tran_id'], val_id=data['val_id'])
        else:
            services.fail_payment(tran_id=data['tran_id'], cancelled=data['status'] == 'CANCELLED')
        return Response(OkResponseSerializer({'ok': True}).data)
