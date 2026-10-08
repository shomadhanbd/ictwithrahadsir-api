"""What every way of recording a paid purchase shares: one buyer at a time, one running purchase per package."""

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.billing.selectors import renewal_window, running_purchase

logger = logging.getLogger("payments")


def lock_buyer(user_id) -> None:
    """Serialises one buyer's purchases, so two at once cannot each miss the other."""
    if user_id:
        get_user_model().objects.select_for_update().filter(pk=user_id).first()


def refuse_running_purchase(user, product) -> None:
    """A package is bought again once its access has ended, or renewed in its last days if it runs for fixed days."""
    running = running_purchase(user, product)
    if running is None:
        return
    if running.access_until is None:
        raise ValidationError({"product_id": "You have already bought this product."})
    until = timezone.localtime(running.access_until)
    if not product.access_days:
        raise ValidationError(
            {"product_id": f"Your access to {product.title} runs until {until:%d %b %Y}; renew it after that."}
        )
    opens = until - renewal_window()
    if timezone.now() < opens:
        message = f"Your access to {product.title} runs until {until:%d %b %Y}; renew it from {opens:%d %b %Y}."
        raise ValidationError({"product_id": message})


def add_note(payment, text) -> None:
    payment.note = f"{payment.note} {text}" if payment.note else text


def flag_if_duplicate(payment) -> bool:
    """Marks a payment for access the buyer already has as refund due; the grant signal skips it.

    The caller holds `lock_buyer` and saves `refund_due` and `note`. A book order is never a duplicate.
    """
    if payment.product_id is None:
        return False
    running = running_purchase(payment.user_id, payment.product_id, exclude=payment)
    if running is None or _renews(payment, running):
        return False
    logger.error("Payment %s duplicates %s -- refund it", payment.transaction_id, running.transaction_id)
    payment.refund_due = True
    add_note(payment, f"Duplicate of {running.transaction_id}: refund.")
    return True


def _renews(payment, running) -> bool:
    """Started in `running`'s renewal window, after it was paid, and runs past it: a renewal, not a second copy."""
    if payment.access_until is None or running.access_until is None:
        return False
    paid_on = running.transaction_date or running.created_at
    opened = running.access_until - renewal_window()
    return payment.created_at > max(paid_on, opened) and payment.access_until > running.access_until
