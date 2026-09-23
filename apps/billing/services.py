"""Every state change billing owns.

These functions are the only place an `Order` or a `Payment` is written. They
take plain keyword arguments and return model instances -- no `request`, no
`Response`, no status codes -- so they can be called from a view, a management
command, or a test without a HTTP layer in the way.

They do raise DRF's `ValidationError` for rule violations. That is deliberate:
the project already routes every error through
`apps.core.api.exception_handler`, which turns that exception into the
`{message, errors}` envelope both frontends parse.

Money moves through SSLCommerz only: `start_payment` opens a session, and
`complete_payment` settles it from what SSLCommerz's validation API says --
never from a callback's own fields.
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework.exceptions import APIException, ValidationError

from apps.billing import sslcommerz
from apps.billing.models import Order, Payment, ProductCoupon
from apps.courses.models import Coupon, Enrollment
from apps.courses.services import access_until, grant_course_access, grant_purchased_access

logger = logging.getLogger('payments')

ZERO = Decimal('0')
CENT = Decimal('0.01')


class PaymentGatewayUnavailable(APIException):
    status_code = 503
    default_detail = 'Online payment is unavailable right now. Please try again shortly.'
    default_code = 'payment_gateway_unavailable'


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def _discount_is_live(discount, discount_till) -> bool:
    return bool(discount) and (not discount_till or discount_till > timezone.now())


def price_after_discount(item) -> Decimal:
    """The payable amount for a `CoursePrice` or a `Product`. `discount` is the amount OFF."""
    if not _discount_is_live(item.discount, item.discount_till):
        return item.amount
    return max(ZERO, item.amount - item.discount)


def coupon_discount(coupon, base) -> Decimal:
    """What a coupon takes off `base`, never more than `base`."""
    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        off = (base * coupon.discount / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        off = coupon.discount
    return min(off, base)


def _not_expired():
    return Q(valid_till__isnull=True) | Q(valid_till__gt=timezone.now())


def _course_coupon(price, code):
    return Coupon.objects.filter(_not_expired(), price=price, code__iexact=code).first()


def _product_coupon(product, code):
    coupon = ProductCoupon.objects.filter(_not_expired(), product=product, code__iexact=code, active=True).first()
    if coupon is None or coupon.usage_limit is None:
        return coupon
    uses = Order.objects.paid().filter(product=product, coupon_code__iexact=coupon.code).count()
    return coupon if uses < coupon.usage_limit else None


def quote(*, user, course=None, price=None, product=None, coupon_code='') -> dict:
    """What an order would cost, and the fields it would be saved with.

    Raises for a coupon that does not apply and a total SSLCommerz would
    refuse. Buying again is allowed: it renews the access.
    """
    if product is not None:
        base = price_after_discount(product)
        titles = {'item_title': product.title, 'price_title': ''}
    else:
        base = price_after_discount(price)
        titles = {'item_title': course.title, 'price_title': price.title}

    code = (coupon_code or '').strip()
    off = ZERO
    if code:
        coupon = _product_coupon(product, code) if product is not None else _course_coupon(price, code)
        if coupon is None:
            raise ValidationError({'coupon_code': ['This coupon is not valid.']})
        code = coupon.code
        off = coupon_discount(coupon, base)

    total = base - off
    if ZERO < total < sslcommerz.MIN_AMOUNT:
        raise ValidationError({'coupon_code': [f'The amount to pay must be at least {sslcommerz.MIN_AMOUNT:g} BDT.']})
    return {**titles, 'base': base, 'coupon_code': code, 'coupon_discount': off, 'total': total}


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@transaction.atomic
def create_order(*, user, course=None, price=None, product=None, coupon_code='') -> Order:
    """Place a pending order for one course (at one of its prices) or one product."""
    q = quote(user=user, course=course, price=price, product=product, coupon_code=coupon_code)
    return Order.objects.create(
        user=user,
        course=course,
        price=price,
        product=product,
        item_title=q['item_title'],
        price_title=q['price_title'],
        coupon_code=q['coupon_code'],
        coupon_discount=q['coupon_discount'],
        amount=q['total'],
        total=q['total'],
        status=Order.Status.PENDING,
    )


def _fulfil(order) -> None:
    """Mark an order paid and grant what it bought. Call inside a transaction.

    Access runs for the price's or the product's validity, and never cuts
    short access the student already has.
    """
    order.status = Order.Status.PAID
    order.save(update_fields=['status'])
    if order.product_id:
        until = order.product.access_until()
        for course in order.product.courses.all():
            grant_purchased_access(user=order.user, course=course, valid_till=until)
    elif order.course:
        until = access_until(order.price) if order.price else None
        grant_purchased_access(user=order.user, course=order.course, valid_till=until)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def _customer(user) -> dict:
    student = getattr(user, 'student', None)
    return {
        'name': user.name or user.phone,
        # SSLCommerz requires an email; many students sign up with a phone only.
        'email': user.email or f'{user.phone}@students.invalid',
        'phone': user.phone or '',
        'address': getattr(student, 'address', ''),
    }


def start_payment(*, order) -> str | None:
    """Open an SSLCommerz session for an order; returns the gateway page URL.

    Returns None when there is nothing to pay (a 100% coupon): the order is
    fulfilled on the spot. A failed or cancelled order may be paid again.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == Order.Status.PAID:
            raise ValidationError({'order_id': ['This order has already been paid.']})

        if order.total == ZERO:
            _fulfil(order)
            return None

        if not sslcommerz.is_configured():
            raise PaymentGatewayUnavailable()

        # An abandoned earlier attempt; SSLCommerz can still report it, and a
        # late VALID for it is honoured in `complete_payment`.
        order.payments.filter(status=Payment.Status.PENDING, val_id='').update(status=Payment.Status.FAILED)
        order.status = Order.Status.PENDING
        order.save(update_fields=['status'])
        # Committed before the HTTP call, so a fast IPN finds it.
        payment = Payment.objects.create(
            order=order,
            amount=order.total,
            transaction_id=uuid.uuid4().hex,
            vendor=Payment.Vendor.SSLCOMMERZ,
            status=Payment.Status.PENDING,
        )

    try:
        return sslcommerz.create_session(
            tran_id=payment.transaction_id,
            amount=payment.amount,
            customer=_customer(order.user),
            product_name=order.item_title or f'Order #{order.pk}',
            product_category='digital-product' if order.product_id else 'course',
        )
    except sslcommerz.SslCommerzError:
        Payment.objects.filter(pk=payment.pk).update(status=Payment.Status.FAILED)
        raise PaymentGatewayUnavailable()


def _held_reason(payment, data) -> str | None:
    """Why a VALID report is not safe to fulfil automatically, or None."""
    if data.get('tran_id') != payment.transaction_id:
        return 'tran_id does not match'
    if data.get('currency_type') != 'BDT':
        return f'currency {data.get("currency_type")}'
    try:
        paid = Decimal(str(data.get('currency_amount')))
    except (ArithmeticError, ValueError):
        return 'unreadable amount'
    if paid != payment.amount:
        return f'amount {paid} for {payment.amount}'
    if int(data.get('risk_level') or 0) == 1:
        return 'flagged risky by SSLCommerz'
    return None


def complete_payment(*, tran_id, val_id) -> Payment:
    """Settle a payment SSLCommerz has reported (success callback or IPN).

    Validated with SSLCommerz first, outside any lock. Safe to call twice --
    the success callback and the IPN usually both arrive. A payment that is
    valid but suspicious (risk flag, amount or currency mismatch) is held
    pending for an admin rather than fulfilled.
    """
    data = sslcommerz.validate(val_id)

    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update()
            .select_related('order')
            .get(transaction_id=tran_id, vendor=Payment.Vendor.SSLCOMMERZ)
        )
        if payment.status == Payment.Status.SUCCESSFUL:
            return payment

        if data.get('status') not in sslcommerz.PAID_STATUSES:
            payment.status = Payment.Status.FAILED
            payment.gateway_response = data
            payment.save(update_fields=['status', 'gateway_response'])
            return payment

        payment.val_id = val_id
        payment.bank_tran_id = data.get('bank_tran_id') or ''
        payment.card_type = data.get('card_type') or ''
        payment.risk_level = int(data.get('risk_level') or 0)
        payment.gateway_response = data

        reason = _held_reason(payment, data)
        if reason:
            logger.error('Payment %s held for review: %s', payment.pk, reason)
            payment.status = Payment.Status.PENDING
        else:
            payment.status = Payment.Status.SUCCESSFUL
        payment.save()

        if payment.status == Payment.Status.SUCCESSFUL:
            order = payment.order
            if order.status == Order.Status.PAID:
                # Paid twice (a second tab). The money is real; refund it by hand.
                logger.warning('Order %s paid again by payment %s; refund it.', order.pk, payment.pk)
            else:
                _fulfil(order)
    return payment


@transaction.atomic
def fail_payment(*, tran_id, cancelled=False) -> Payment:
    """The student's payment failed or they cancelled it at the gateway.

    Needs no validation call: it only touches a payment SSLCommerz has not yet
    reported, and a later VALID report still settles it.
    """
    payment = (
        Payment.objects.select_for_update()
        .select_related('order')
        .get(transaction_id=tran_id, vendor=Payment.Vendor.SSLCOMMERZ)
    )
    if payment.status == Payment.Status.PENDING and not payment.val_id:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=['status'])
        order = payment.order
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.CANCELLED if cancelled else Order.Status.FAILED
            order.save(update_fields=['status'])
    return payment


@transaction.atomic
def confirm_payment(*, payment, status, confirm_amount_mismatch: bool = False) -> Payment:
    """An admin's decision on a payment: release a held one, or fail it.

    An SSLCommerz payment the gateway never reported cannot be confirmed --
    there is no money behind it to release.
    """
    if status == Payment.Status.SUCCESSFUL and payment.vendor == Payment.Vendor.SSLCOMMERZ and not payment.val_id:
        raise ValidationError({'status': ['SSLCommerz never reported this payment, so it cannot be confirmed.']})

    if status == Payment.Status.SUCCESSFUL and payment.amount != payment.order.amount:
        # `confirm_amount_mismatch` is the deliberate override for a genuine
        # part payment or a corrected amount.
        if not confirm_amount_mismatch:
            raise ValidationError(
                {
                    'amount': [
                        f'This payment records {payment.amount} but the order is for '
                        f'{payment.order.amount}. Re-send with '
                        f'confirm_amount_mismatch=true to accept it anyway.'
                    ]
                }
            )

    payment.status = status
    payment.save(update_fields=['status'])

    order = payment.order
    if status == Payment.Status.SUCCESSFUL and order.status != Order.Status.PAID:
        _fulfil(order)
    elif status == Payment.Status.FAILED and order.status != Order.Status.PAID:
        order.status = Order.Status.FAILED
        order.save(update_fields=['status'])

    return payment


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------


def claim_free_course(*, user, course) -> Enrollment:
    """Self-enrol on a course that costs nothing.

    A course with no prices at all is treated as free; one with prices must
    offer a zero-cost option.
    """
    free_price = course.prices.filter(amount=0).first()
    if not free_price and course.prices.exists():
        raise ValidationError({'course_id': ['This course is not free.']})

    return grant_course_access(user=user, course=course, payment_type=Enrollment.PaymentType.FREE)
