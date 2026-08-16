import json
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet
from apps.courses.models import Course, CoursePrice, CourseUser
from apps.shop.api.v1.serializers import (
    AdminPaymentSerializer,
    CartItemSerializer,
    OrderSerializer,
    PaymentSerializer,
    ProductSerializer,
)
from apps.shop.models import CartItem, Order, Payment, Product


class AdminProductViewSet(AdminModelViewSet):
    """Not present in the current admin-panel UI yet, but added so the shop
    actually has a management surface -- an industry-standard API shouldn't
    leave `Product` writable only via direct DB access."""

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = 'slug'


# ---------------------------------------------------------------------------
# Public catalog
# ---------------------------------------------------------------------------


class PublicProductListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    pagination_class = LaravelStylePageNumberPagination
    queryset = Product.objects.filter(active=True)


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class BaseCartAPIView(APIView):
    """Every cart endpoint answers with the caller's whole cart, so the
    client never has to reconcile a partial update."""

    permission_classes = [IsAuthenticated]

    def cart_response(self):
        items = CartItem.objects.filter(user=self.request.user).select_related('product')
        return Response(CartItemSerializer(items, many=True).data)


class CartItemAPIView(BaseCartAPIView):
    """POST /cart/items/ -- put a product in the cart."""

    def post(self, request):
        product = Product.objects.filter(
            pk=request.data.get('product_id'), active=True
        ).first()
        if not product:
            raise ValidationError({'product_id': ['Product not found.']})

        item, created = CartItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.quantity += 1
            item.save(update_fields=['quantity'])
        return self.cart_response()


class CartAPIView(CartItemAPIView):
    """GET /cart/ -- the caller's cart.

    Inherits POST so the legacy `POST /cart` add still works.
    """

    def get(self, request):
        return self.cart_response()


class CartItemDetailAPIView(BaseCartAPIView):
    """One line in the cart: PATCH adjusts the quantity, DELETE removes it."""

    def patch(self, request, product_id):
        return self.adjust_quantity(request, product_id, request.data.get('action'))

    def delete(self, request, product_id):
        CartItem.objects.filter(user=request.user, product_id=product_id).delete()
        return self.cart_response()

    def adjust_quantity(self, request, product_id, action):
        item = CartItem.objects.filter(user=request.user, product_id=product_id).first()
        if not item:
            raise NotFound('Item is not in the cart.')

        if action == 'increment':
            item.quantity += 1
            item.save(update_fields=['quantity'])
        elif action == 'decrement':
            item.quantity -= 1
            if item.quantity <= 0:
                item.delete()
            else:
                item.save(update_fields=['quantity'])
        else:
            raise ValidationError({'action': ['Must be `increment` or `decrement`.']})

        return self.cart_response()


class CartAddRemoveAPIView(CartItemDetailAPIView):
    """Legacy `POST /cart/add-remove` -- product id and action in the body."""

    def post(self, request):
        return self.adjust_quantity(
            request, request.data.get('product_id'), request.data.get('action')
        )


class CartDeleteAPIView(CartItemDetailAPIView):
    """Legacy `DELETE /cart/delete/<product_id>`."""


# ---------------------------------------------------------------------------
# Purchases / orders / payments
# ---------------------------------------------------------------------------


def price_after_discount(price: CoursePrice) -> Decimal:
    amount = price.amount
    if price.discount and (not price.discount_till or price.discount_till > timezone.now()):
        amount = max(Decimal('0'), amount - price.discount)
    return amount


class FreeEnrollmentAPIView(APIView):
    """Self-enrolment on a course that has a zero-cost price.

    Named for what it creates. The legacy path called it
    `free-course-purchase`, though nothing is purchased.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        course = Course.objects.filter(pk=request.data.get('course_id'), active=True).first()
        if not course:
            raise NotFound('Course not found.')

        free_price = course.prices.filter(amount=0).first()
        if not free_price and course.prices.exists():
            raise ValidationError({'course_id': ['This course is not free.']})

        CourseUser.objects.update_or_create(
            course=course,
            user=request.user,
            defaults={'payment_type': CourseUser.PaymentType.FREE},
        )
        return Response({'ok': True, 'course_id': course.id})


class FreeCoursePurchaseAPIView(FreeEnrollmentAPIView):
    """Legacy `POST /free-course-purchase`."""


class OrderAPIView(APIView):
    """GET lists the caller's orders, POST places one.

    The legacy API split these across a singular `order` and a plural
    `orders`, which read as two different resources.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(user=request.user)
        return Response({'data': OrderSerializer(orders, many=True).data})

    def post(self, request):
        course_id = request.data.get('course_id')
        course = Course.objects.filter(pk=course_id, active=True).first()
        price = (
            CoursePrice.objects.filter(
                pk=request.data.get('price_id'),
                priceable_type=CoursePrice.PRICEABLE_COURSE,
                priceable_id=course_id,
            ).first()
            if course
            else None
        )
        if not course or not price:
            raise ValidationError({'price_id': ['Invalid course/price selection.']})

        amount = price_after_discount(price)
        order = Order.objects.create(
            user=request.user,
            course=course,
            price=price,
            item_title=course.title,
            price_title=price.title,
            amount=amount,
            total=amount,
            status=Order.Status.PENDING,
        )
        return Response(
            {'id': order.id, 'order': OrderSerializer(order).data},
            status=status.HTTP_201_CREATED,
        )


class PaymentSubmitAPIView(APIView):
    """Records a manual mobile-banking transfer against an order. An admin
    confirms it later; nothing here marks the order paid."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        order = Order.objects.filter(
            pk=request.data.get('order_id'), user=request.user
        ).first()
        if not order:
            raise NotFound('Order not found.')
        if order.status == Order.Status.PAID:
            raise ValidationError({'order_id': ['This order has already been paid.']})

        details = self._parse_details(request.data.get('details'))
        transaction_id = str(request.data.get('transaction_id') or '').strip()

        # Checked here as well as by the DB constraint so a reused TrxID comes
        # back as a validation error rather than an IntegrityError 500.
        if transaction_id and Payment.objects.filter(transaction_id=transaction_id).exists():
            raise ValidationError(
                {'transaction_id': ['This transaction ID has already been submitted.']}
            )

        payment = Payment.objects.create(
            order=order,
            # Always the order's own amount. This used to be
            # `request.data.get('amount') or order.amount`, so the client
            # decided what a payment was worth and could record ৳1 against a
            # ৳4,000 order.
            amount=order.amount,
            transaction_id=transaction_id,
            vendor=details.get('vendor', Payment.Vendor.BKASH),
            sent_from=details.get('sent_from', ''),
            sent_to=details.get('sent_to', ''),
            status=Payment.Status.PENDING,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    def _parse_details(self, raw):
        # The client posts this as a JSON string in multipart submissions and
        # as a real object in JSON ones.
        try:
            return json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, ValueError):
            raise ValidationError({'details': ['Must be valid JSON.']})


class OrderCreateAPIView(OrderAPIView):
    """Legacy `POST /order`."""


class MyOrderListAPIView(OrderAPIView):
    """Legacy `GET /orders`."""


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminPaymentListAPIView(ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdminPaymentSerializer
    pagination_class = LaravelStylePageNumberPagination
    queryset = Payment.objects.select_related('order', 'order__user')


class AdminPaymentUpdateAPIView(APIView):
    """Confirming a payment is what actually grants course access."""

    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        payment = Payment.objects.filter(pk=pk).first()
        if not payment:
            raise NotFound('Payment not found.')

        status_value = request.data.get('status')
        if status_value not in Payment.Status.values:
            raise ValidationError({'status': ['Invalid status.']})

        # Confirming is what grants course access, so it should not be
        # possible to do it by accident against a payment that does not cover
        # the order. New payments always carry the order's own amount, but
        # rows created before that fix may not -- and the client used to
        # choose the figure. `confirm_amount_mismatch` is the deliberate
        # override for a genuine part payment or a corrected amount.
        if (
            status_value == Payment.Status.SUCCESSFUL
            and payment.amount != payment.order.amount
            and not request.data.get('confirm_amount_mismatch')
        ):
            raise ValidationError(
                {
                    'amount': [
                        f'This payment records {payment.amount} but the order is for '
                        f'{payment.order.amount}. Re-send with '
                        f'confirm_amount_mismatch=true to accept it anyway.'
                    ]
                }
            )

        payment.status = status_value
        payment.save(update_fields=['status'])

        order = payment.order
        if status_value == Payment.Status.SUCCESSFUL:
            order.status = Order.Status.PAID
            order.save(update_fields=['status'])
            if order.course:
                CourseUser.objects.update_or_create(
                    course=order.course,
                    user=order.user,
                    defaults={'payment_type': CourseUser.PaymentType.PAID},
                )
        elif status_value == Payment.Status.FAILED:
            order.status = Order.Status.FAILED
            order.save(update_fields=['status'])

        return Response(AdminPaymentSerializer(payment).data)
