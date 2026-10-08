"""Sales taken at the centre and payments staff settle by hand."""

from django.db import transaction
from django.utils import timezone

from apps.billing.models import Payment
from apps.billing.selectors import access_until
from apps.billing.services.settlement import add_note, flag_if_duplicate, lock_buyer, refuse_running_purchase


@transaction.atomic
def record_cash_sale(*, user, product, amount, valid_till, recorded_by, note=""):
    """A paid, VALID payment; the post-save signal grants access and texts the buyer.

    Without `valid_till` the sale lasts as long as the package does: lifetime only for a lifetime package.
    Like an online purchase, it is refused while the buyer's access to the package is still running.
    """
    lock_buyer(user.pk)
    refuse_running_purchase(user, product)
    return Payment.objects.create(
        user=user,
        product=product,
        amount=amount,
        access_until=valid_till or access_until(product, user=user),
        status=Payment.Status.VALID,
        method=Payment.Method.CASH,
        transaction_date=timezone.now(),
        recorded_by=recorded_by,
        note=note,
    )


@transaction.atomic
def mark_payment_paid(payment, *, by):
    """Settles a payment staff confirmed by hand; saving `status` is what grants access.

    Returns None, changing nothing, for a payment already paid or whose buyer's account is gone.
    """
    lock_buyer(payment.user_id)
    payment = Payment.objects.select_for_update().select_related("product").get(pk=payment.pk)
    if payment.status == Payment.Status.VALID or payment.user_id is None:
        return None
    payment.status = Payment.Status.VALID
    payment.transaction_date = payment.transaction_date or timezone.now()
    add_note(payment, f"Marked paid by {by}.")
    if payment.product_id is not None:
        # Access runs from now, or from the end of the purchase it renews: the checkout may have been started days ago.
        started_with = payment.access_until
        payment.access_until = access_until(payment.product, user=payment.user_id)
        if flag_if_duplicate(payment):
            payment.access_until = started_with
    payment.save(update_fields=["status", "access_until", "transaction_date", "note", "refund_due", "updated_at"])
    return payment
