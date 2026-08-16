import json
from decimal import Decimal

from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.courses.models import Course, CoursePrice, CourseUser
from django.utils import timezone

from apps.core.api.viewsets import AdminModelViewSet

from .models import CartItem, Order, Payment, Product
from .serializers import (
    AdminPaymentSerializer,
    CartItemSerializer,
    OrderSerializer,
    PaymentSerializer,
    ProductSerializer,
)


class AdminProductViewSet(AdminModelViewSet):
    """Not present in the current admin-panel UI yet, but added so the shop
    actually has a management surface -- an industry-standard API shouldn't
    leave `Product` writable only via direct DB access."""

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = "slug"

# ---------------------------------------------------------------------------
# Public catalog
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([AllowAny])
def public_product_list(request):
    qs = Product.objects.filter(active=True)
    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(ProductSerializer(page, many=True).data)


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def cart(request):
    if request.method == "GET":
        items = CartItem.objects.filter(user=request.user).select_related("product")
        return Response(CartItemSerializer(items, many=True).data)

    product_id = request.data.get("product_id")
    product = Product.objects.filter(pk=product_id, active=True).first()
    if not product:
        raise ValidationError({"product_id": ["Product not found."]})
    item, created = CartItem.objects.get_or_create(user=request.user, product=product)
    if not created:
        item.quantity += 1
        item.save()
    items = CartItem.objects.filter(user=request.user).select_related("product")
    return Response(CartItemSerializer(items, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cart_add_remove(request):
    product_id = request.data.get("product_id")
    action = request.data.get("action")
    item = CartItem.objects.filter(user=request.user, product_id=product_id).first()
    if not item:
        raise NotFound("Item is not in the cart.")
    if action == "increment":
        item.quantity += 1
        item.save()
    elif action == "decrement":
        item.quantity -= 1
        if item.quantity <= 0:
            item.delete()
        else:
            item.save()
    else:
        raise ValidationError({"action": ["Must be `increment` or `decrement`."]})
    items = CartItem.objects.filter(user=request.user).select_related("product")
    return Response(CartItemSerializer(items, many=True).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def cart_delete(request, product_id):
    CartItem.objects.filter(user=request.user, product_id=product_id).delete()
    items = CartItem.objects.filter(user=request.user).select_related("product")
    return Response(CartItemSerializer(items, many=True).data)


# ---------------------------------------------------------------------------
# Purchases / orders / payments
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def free_course_purchase(request):
    course_id = request.data.get("course_id")
    course = Course.objects.filter(pk=course_id, active=True).first()
    if not course:
        raise NotFound("Course not found.")
    free_price = course.prices.filter(amount=0).first()
    if not free_price and course.prices.exists():
        raise ValidationError({"course_id": ["This course is not free."]})

    enrollment, _ = CourseUser.objects.update_or_create(
        course=course,
        user=request.user,
        defaults={"payment_type": CourseUser.PaymentType.FREE},
    )
    return Response({"ok": True, "course_id": course.id})


def _price_after_discount(price: CoursePrice) -> Decimal:
    amount = price.amount
    if price.discount and (not price.discount_till or price.discount_till > timezone.now()):
        amount = max(Decimal("0"), amount - price.discount)
    return amount


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_order(request):
    course_id = request.data.get("course_id")
    price_id = request.data.get("price_id")
    course = Course.objects.filter(pk=course_id, active=True).first()
    price = (
        CoursePrice.objects.filter(
            pk=price_id, priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=course_id
        ).first()
        if course
        else None
    )
    if not course or not price:
        raise ValidationError({"price_id": ["Invalid course/price selection."]})

    amount = _price_after_discount(price)
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
    return Response({"id": order.id, "order": OrderSerializer(order).data}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_payment(request):
    order_id = request.data.get("order_id")
    order = Order.objects.filter(pk=order_id, user=request.user).first()
    if not order:
        raise NotFound("Order not found.")
    if order.status == Order.Status.PAID:
        raise ValidationError({"order_id": ["This order has already been paid."]})

    details_raw = request.data.get("details")
    try:
        details = json.loads(details_raw) if isinstance(details_raw, str) else (details_raw or {})
    except (TypeError, ValueError):
        raise ValidationError({"details": ["Must be valid JSON."]})

    payment = Payment.objects.create(
        order=order,
        amount=request.data.get("amount") or order.amount,
        transaction_id=request.data.get("transaction_id", ""),
        vendor=details.get("vendor", Payment.Vendor.BKASH),
        sent_from=details.get("sent_from", ""),
        sent_to=details.get("sent_to", ""),
        status=Payment.Status.PENDING,
    )
    return Response(PaymentSerializer(payment).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    orders = Order.objects.filter(user=request.user)
    return Response({"data": OrderSerializer(orders, many=True).data})


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_payment_list(request):
    payments = Payment.objects.select_related("order", "order__user")
    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(payments, request)
    return paginator.get_paginated_response(AdminPaymentSerializer(page, many=True).data)


@api_view(["PATCH"])
@permission_classes([IsAdminRole])
def admin_payment_update(request, pk):
    payment = Payment.objects.filter(pk=pk).first()
    if not payment:
        raise NotFound("Payment not found.")
    status_value = request.data.get("status")
    if status_value not in Payment.Status.values:
        raise ValidationError({"status": ["Invalid status."]})

    payment.status = status_value
    payment.save()

    order = payment.order
    if status_value == Payment.Status.SUCCESSFUL:
        order.status = Order.Status.PAID
        order.save()
        if order.course:
            CourseUser.objects.update_or_create(
                course=order.course,
                user=order.user,
                defaults={"payment_type": CourseUser.PaymentType.PAID},
            )
    elif status_value == Payment.Status.FAILED:
        order.status = Order.Status.FAILED
        order.save()

    return Response(AdminPaymentSerializer(payment).data)
