"""Texts sent to buyers."""

import logging

from django.conf import settings
from django.utils import timezone

from apps.billing.models import Payment
from apps.core.bangla import bn_date
from apps.core.sms import get_sms_backend

logger = logging.getLogger("billing")


def purchase_confirmation(payment) -> str:
    access = f"{bn_date(payment.access_until)} পর্যন্ত" if payment.access_until else "আজীবন"
    return (
        f"ধন্যবাদ! {payment.title} কেনা সম্পন্ন হয়েছে। এক্সেস: {access}। "
        f"শেখা শুরু করুন: {settings.FRONTEND_URL.rstrip('/')}/my-courses"
    )


def send_purchase_confirmation(payment_id) -> bool:
    """Texts the buyer once per payment; a failed send is logged, never raised."""
    claimed = Payment.objects.filter(
        pk=payment_id, status=Payment.Status.VALID, confirmation_sent_at__isnull=True, user__isnull=False
    ).update(confirmation_sent_at=timezone.now())
    if not claimed:
        return False
    payment = Payment.objects.select_related("user", "product").get(pk=payment_id)
    try:
        get_sms_backend().send(payment.user.phone, purchase_confirmation(payment))
    except Exception:
        logger.exception("Purchase confirmation SMS failed for payment %s", payment.transaction_id)
        return False
    return True
