from django.conf import settings
from django.db import models

from apps.core.models import OrderedModel, TimestampModel
from apps.courses.models import Course, CoursePrice


class Order(TimestampModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    price = models.ForeignKey(
        CoursePrice, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    product = models.ForeignKey(
        "store.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    quantity = models.PositiveIntegerField(default=1)
    item_title = models.CharField(max_length=255, blank=True)
    price_title = models.CharField(max_length=150, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.pk} ({self.user})"


class Payment(TimestampModel):
    class Vendor(models.TextChoices):
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_id = models.CharField(max_length=100, db_index=True)
    vendor = models.CharField(max_length=20, choices=Vendor.choices, default=Vendor.BKASH)
    sent_from = models.CharField(max_length=20, blank=True)
    sent_to = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A mobile-banking TrxID identifies exactly one real transfer, so
            # it must not be claimed twice -- otherwise a student can reuse a
            # TrxID they have seen elsewhere and an admin confirming it grants
            # course access for a transfer that was never made to us.
            # Blank is excluded because the API allows submitting without one.
            models.UniqueConstraint(
                fields=["transaction_id"],
                condition=~models.Q(transaction_id=""),
                name="unique_non_blank_payment_transaction_id",
            )
        ]

    def __str__(self):
        return f"Payment for order #{self.order_id}"

    @property
    def details(self):
        return {"vendor": self.vendor, "sent_from": self.sent_from, "sent_to": self.sent_to}
