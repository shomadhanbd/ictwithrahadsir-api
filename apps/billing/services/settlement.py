"""What every way of recording a paid purchase shares: one buyer at a time, one running purchase per package."""

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.billing.selectors import running_purchase

logger = logging.getLogger("payments")


def lock_buyer(user_id) -> None:
    """Serialises one buyer's purchases, so two at once cannot each miss the other."""
    if user_id:
        get_user_model().objects.select_for_update().filter(pk=user_id).first()


def refuse_running_purchase(user, product) -> None:
    """A package is bought again only once its access has ended."""
    running = running_purchase(user, product)
    if running is None:
        return
    if running.access_until is None:
        raise ValidationError({"product_id": "You have already bought this product."})
    until = timezone.localtime(running.access_until)
    raise ValidationError(
        {"product_id": f"Your access to {product.title} runs until {until:%d %b %Y}; renew it after that."}
    )


def add_note(payment, text) -> None:
    payment.note = f"{payment.note} {text}" if payment.note else text


def flag_if_duplicate(payment) -> bool:
    """Marks a payment for access the buyer already has as refund due; the grant signal skips it.

    The caller holds `lock_buyer` and saves `refund_due` and `note`.
    """
    running = running_purchase(payment.user_id, payment.product_id, exclude=payment)
    if running is None:
        return False
    logger.error("Payment %s duplicates %s -- refund it", payment.transaction_id, running.transaction_id)
    payment.refund_due = True
    add_note(payment, f"Duplicate of {running.transaction_id}: refund.")
    return True
