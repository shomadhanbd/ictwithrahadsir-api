import json
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth
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
from apps.store.models import Product
from apps.courses.models import Course, CoursePrice, Enrollment
from apps.courses.services import grant_course_access
from apps.billing.api.v1.serializers import (
    AdminPaymentSerializer,
    OrderSerializer,
    PaymentSerializer,
)
from apps.billing.models import Order, Payment


# ---------------------------------------------------------------------------
# Purchases / orders / payments
# ---------------------------------------------------------------------------


def price_after_discount(price: CoursePrice) -> Decimal:
    amount = price.amount
    if price.discount and (not price.discount_till or price.discount_till > timezone.now()):
        amount = max(Decimal('0'), amount - price.discount)
    return amount


def product_price_after_discount(product) -> Decimal:
    """Same rule as a course price: `discount` is the amount OFF.

    The store had no server-side total at all until orders learned about
    products, so the meaning of `Product.discount` was decided only by the
    seed — which wrote a sale price, the opposite of what `CoursePrice` means
    by the same field name. One field name with two meanings in one API is a
    trap for every consumer, so products follow the course rule and the seed
    was corrected to match.
    """
    amount = product.price
    if product.discount and (
        not product.discount_till or product.discount_till > timezone.now()
    ):
        amount = max(Decimal('0'), amount - product.discount)
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

        # Enrolling is a courses operation; go through its service rather
        # than writing another app's table.
        grant_course_access(
            user=request.user, course=course, payment_type=Enrollment.PaymentType.FREE
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
        # A product order and a course order are the same resource with a
        # different item; the model has carried `product` and `quantity` from
        # the start and only this endpoint never used them.
        if request.data.get('product_id'):
            return self._create_product_order(request)

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

    def _create_product_order(self, request):
        product = Product.objects.filter(
            pk=request.data.get('product_id'), active=True
        ).first()
        if not product:
            raise ValidationError({'product_id': ['Unknown product.']})

        try:
            quantity = int(request.data.get('quantity', 1))
        except (TypeError, ValueError):
            raise ValidationError({'quantity': ['Must be a whole number.']})
        if quantity < 1:
            raise ValidationError({'quantity': ['Must be at least 1.']})

        # Stock is the whole point of holding it: an order that cannot be
        # fulfilled should fail here rather than at the packing table.
        if product.stock < quantity:
            raise ValidationError(
                {'quantity': [f'Only {product.stock} left in stock.']}
            )

        unit = product_price_after_discount(product)
        total = unit * quantity
        order = Order.objects.create(
            user=request.user,
            product=product,
            quantity=quantity,
            item_title=product.name,
            amount=unit,
            total=total,
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
    # The panel searches by payer and by transaction reference; without these
    # the global SearchFilter had nothing to match and `?search=` was ignored.
    search_fields = ['transaction_id', 'order__user__name', 'order__user__phone']

    def get_queryset(self):
        # Newest first, and explicitly ordered: an unordered queryset lets the
        # database pick page boundaries, so a payment could show on two pages
        # or on none.
        qs = Payment.objects.select_related('order', 'order__user').order_by('-id')

        # The screen's main job is clearing pending payments, which is
        # impossible on a mixed list once there are more than a page of them.
        status_value = self.request.query_params.get('status')
        if status_value and status_value != 'all':
            qs = qs.filter(status=status_value)
        return qs


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
                grant_course_access(
                    user=order.user,
                    course=order.course,
                    payment_type=Enrollment.PaymentType.PAID,
                )
        elif status_value == Payment.Status.FAILED:
            order.status = Order.Status.FAILED
            order.save(update_fields=['status'])

        return Response(AdminPaymentSerializer(payment).data)


# ---------------------------------------------------------------------------
# Admin dashboard
#
# Lives here because three of its four payloads are order and revenue
# aggregates. It also counts courses and students, but billing already
# depends on both of those apps for Order.course and Order.user, so this
# adds no new dependency edge.
# ---------------------------------------------------------------------------


def _month_start(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _year_start(now):
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


class AdminDashboardAPIView(APIView):
    """Headline counters for the admin panel's landing page."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        from apps.identity.models import User
        from apps.courses.models import Course
        now = timezone.now()
        month_start = _month_start(now)
        year_start = _year_start(now)

        paid_orders = Order.objects.filter(status=Order.Status.PAID)

        def income_since(since):
            total = paid_orders.filter(created_at__gte=since).aggregate(total=Sum('amount'))
            return total['total'] or 0

        def orders_since(status, since):
            return Order.objects.filter(status=status, created_at__gte=since).count()

        def students_since(since):
            return User.objects.filter(role=User.Role.STUDENT, date_joined__gte=since).count()

        return Response(
            {
                'income': {
                    'thisMonth': income_since(month_start),
                    'thisYear': income_since(year_start),
                    'lifeTime': paid_orders.aggregate(total=Sum('amount'))['total'] or 0,
                },
                'orders': {
                    'completed': {
                        'thisMonth': orders_since(Order.Status.PAID, month_start),
                        'thisYear': orders_since(Order.Status.PAID, year_start),
                    },
                    'incomplete': {
                        'thisMonth': orders_since(Order.Status.PENDING, month_start),
                        'thisYear': orders_since(Order.Status.PENDING, year_start),
                    },
                },
                'totalCounts': {
                    'courses': Course.objects.filter(active=True).count(),
                    'students': User.objects.filter(role=User.Role.STUDENT).count(),
                },
                'studentsRegistered': {
                    'thisMonth': students_since(month_start),
                    'thisYear': students_since(year_start),
                },
            }
        )


class AdminDashboardSalesOverviewAPIView(APIView):
    """Paid-order counts per month for the last year."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        start = timezone.now().replace(day=1) - timezone.timedelta(days=365)
        rows = (
            Order.objects.filter(status=Order.Status.PAID, created_at__gte=start)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        return Response(
            {
                'months': [row['month'].strftime('%Y-%m') for row in rows],
                'courseSales': [row['count'] for row in rows],
            }
        )


class AdminDashboardPaymentChartAPIView(APIView):
    """Paid-order income per day for the last 30 days."""

    permission_classes = [IsAdminRole]

    def get(self, request):
        start = timezone.now() - timezone.timedelta(days=30)
        rows = (
            Order.objects.filter(status=Order.Status.PAID, created_at__gte=start)
            .annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(total=Sum('amount'))
            .order_by('day')
        )
        return Response(
            {
                'allDays': [row['day'].strftime('%Y-%m-%d') for row in rows],
                'income': [float(row['total'] or 0) for row in rows],
            }
        )
