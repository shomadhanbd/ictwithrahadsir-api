"""Every state change billing owns.

These functions are the only place an `Order` or a `Payment` is written. They
take plain keyword arguments and return model instances -- no `request`, no
`Response`, no status codes -- so they can be called from a view, a management
command, or a test without a HTTP layer in the way.

They do raise DRF's `ValidationError` for rule violations. That is deliberate:
the project already routes every error through
`apps.core.api.exception_handler`, which turns that exception into the
`{message, errors}` envelope both frontends parse. Inventing a parallel
hierarchy of domain exceptions here would mean translating them back into the
same DRF exception at every call site.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from apps.billing.models import Order, Payment
from apps.courses.models import Enrollment
from apps.courses.services import grant_course_access

# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def _discount_is_live(discount, discount_till) -> bool:
    return bool(discount) and (not discount_till or discount_till > timezone.now())


def price_after_discount(price) -> Decimal:
    """The payable amount for a `CoursePrice`. `discount` is the amount OFF."""
    if not _discount_is_live(price.discount, price.discount_till):
        return price.amount
    return max(Decimal('0'), price.amount - price.discount)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@transaction.atomic
def create_course_order(*, user, course, price) -> Order:
    """Place a pending order for a course at one of its prices."""
    amount = price_after_discount(price)
    return Order.objects.create(
        user=user,
        course=course,
        price=price,
        item_title=course.title,
        price_title=price.title,
        amount=amount,
        total=amount,
        status=Order.Status.PENDING,
    )


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@transaction.atomic
def submit_payment(*, order, transaction_id: str, details: dict) -> Payment:
    """Record a manual mobile-banking transfer against an order.

    Nothing here marks the order paid; an admin confirms it later through
    `confirm_payment`.
    """
    if order.status == Order.Status.PAID:
        raise ValidationError({'order_id': ['This order has already been paid.']})

    # Checked here as well as by the DB constraint so a reused TrxID comes
    # back as a validation error rather than an IntegrityError 500.
    if transaction_id and Payment.objects.filter(transaction_id=transaction_id).exists():
        raise ValidationError({'transaction_id': ['This transaction ID has already been submitted.']})

    return Payment.objects.create(
        order=order,
        # Always the order's own amount. This used to be
        # `request.data.get('amount') or order.amount`, so the client decided
        # what a payment was worth and could record 1 against a 4,000 order.
        amount=order.amount,
        transaction_id=transaction_id,
        vendor=details.get('vendor', Payment.Vendor.BKASH),
        sent_from=details.get('sent_from', ''),
        sent_to=details.get('sent_to', ''),
        status=Payment.Status.PENDING,
    )


@transaction.atomic
def confirm_payment(*, payment, status, confirm_amount_mismatch: bool = False) -> Payment:
    """Move a payment to `status` and carry the order and enrolment with it.

    This is the money path: confirming a payment is what grants a student
    access to a paid course. It touches three rows across two apps -- the
    payment, its order, and an enrolment -- so it runs in one transaction.
    Without that, a failure partway through leaves a payment marked successful
    against an unpaid order, or a paid order with no enrolment behind it.
    """
    if status == Payment.Status.SUCCESSFUL and payment.amount != payment.order.amount:
        # New payments always carry the order's own amount, but rows created
        # before that fix may not -- and the client used to choose the figure.
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
    if status == Payment.Status.SUCCESSFUL:
        order.status = Order.Status.PAID
        order.save(update_fields=['status'])
        if order.course:
            # Enrolling is a courses operation; go through its service rather
            # than writing another app's table.
            grant_course_access(
                user=order.user,
                course=order.course,
                payment_type=Enrollment.PaymentType.PAID,
            )
    elif status == Payment.Status.FAILED:
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
