from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.billing.models import Payment
from apps.billing.notifications import send_purchase_confirmation
from apps.courses.services import grant_purchased_access


@receiver(post_save, sender=Payment, dispatch_uid="billing.payment_post_save_grant_access")
def grant_access_on_valid(sender, instance: Payment, created, update_fields=None, **kwargs):
    if instance.status != Payment.Status.VALID:
        return
    if not created and (update_fields is None or "status" not in update_fields):
        return
    if instance.refund_due:
        return

    def _commit():
        if instance.user_id:
            for course in instance.unlocked_courses():
                grant_purchased_access(user=instance.user, course=course, valid_till=instance.access_until)
            send_purchase_confirmation(instance.pk)

    transaction.on_commit(_commit)
