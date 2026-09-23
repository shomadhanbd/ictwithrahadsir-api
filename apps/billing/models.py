from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.billing.managers import OrderQuerySet, PaymentQuerySet
from apps.core.models import TimestampModel
from apps.core.slugs import unique_slug
from apps.courses.models import Coupon, Course, CoursePrice


class Product(TimestampModel):
    """A one-time purchase that unlocks one or more courses, live or recorded.

    Priced like a `CoursePrice`: `discount` is the amount *off*, live until
    `discount_till`. Access lasts `access_days` from purchase, or until
    `access_ends_on` -- at most one of them; neither means lifetime.
    """

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField(blank=True)
    thumbnail = models.URLField(max_length=500, blank=True)
    #: What buying it unlocks.
    courses = models.ManyToManyField(Course, related_name="products")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_till = models.DateTimeField(null=True, blank=True)
    #: Days of access from purchase, e.g. 365 for a recorded course.
    access_days = models.PositiveIntegerField(null=True, blank=True)
    #: The last day of access, e.g. when a live batch ends.
    access_ends_on = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(access_days__isnull=True) | models.Q(access_ends_on__isnull=True),
                name="product_access_is_days_or_end_date",
            )
        ]

    def __str__(self):
        return self.title

    def access_until(self):
        """When access bought now ends; None for lifetime."""
        if self.access_ends_on:
            # The whole of the last day, in the site's time zone.
            return timezone.make_aware(datetime.combine(self.access_ends_on, time.max))
        if self.access_days:
            return timezone.now() + timedelta(days=self.access_days)
        return None

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*args, **kwargs)


class ProductCoupon(TimestampModel):
    """A code that takes money off one product.

    Uses are not counted on the row: they are the paid orders carrying this
    product and code, so there is no counter to drift.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="coupons")
    code = models.CharField(max_length=50)
    #: The same choices as a course coupon's, so the schema keeps one enum.
    discount_type = models.CharField(
        max_length=20, choices=Coupon.DiscountType.choices, default=Coupon.DiscountType.PERCENT
    )
    discount = models.DecimalField(max_digits=10, decimal_places=2)
    valid_till = models.DateTimeField(null=True, blank=True)
    #: Blank for unlimited.
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["product", "code"], name="unique_coupon_code_per_product")]

    def __str__(self):
        return f"{self.code} ({self.product})"


class Order(TimestampModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    price = models.ForeignKey(CoursePrice, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    #: PROTECT: a product somebody paid for is retired with `active`, not deleted.
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True, related_name="orders")
    #: Always 1: an order is one course or one product.
    quantity = models.PositiveIntegerField(default=1)
    item_title = models.CharField(max_length=255, blank=True)
    price_title = models.CharField(max_length=150, blank=True)
    #: The code as applied, whichever kind of coupon it was; blank for none.
    coupon_code = models.CharField(max_length=50, blank=True)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    #: Both are what the student pays, after every discount.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # `has_order` on every course payload asks exactly this pair.
            models.Index(fields=["user", "course"]),
            # "My products", and whether a product is already owned.
            models.Index(fields=["user", "product"]),
            # Revenue and order counts filter on a status plus a date floor.
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(course__isnull=False, product__isnull=False),
                name="order_is_one_course_or_one_product",
            )
        ]

    def __str__(self):
        return f"Order #{self.pk} ({self.user})"


class Payment(TimestampModel):
    class Vendor(models.TextChoices):
        SSLCOMMERZ = "sslcommerz", "SSLCommerz"
        # The manual mobile-banking flow these name is retired; old rows keep them.
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Successful"
        FAILED = "failed", "Failed"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    #: For an SSLCommerz payment, the `tran_id` we generate and send them.
    transaction_id = models.CharField(max_length=100, db_index=True)
    vendor = models.CharField(max_length=20, choices=Vendor.choices, default=Vendor.SSLCOMMERZ)
    sent_from = models.CharField(max_length=20, blank=True)
    sent_to = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # -- set from SSLCommerz's validation API --------------------------------
    #: Present once SSLCommerz has reported the payment; a pending payment
    #: with one is waiting for an admin (a risk flag or a mismatch).
    val_id = models.CharField(max_length=100, blank=True)
    bank_tran_id = models.CharField(max_length=100, blank=True)
    #: How the student paid inside the gateway, e.g. "BKASH-BKash".
    card_type = models.CharField(max_length=50, blank=True)
    risk_level = models.PositiveSmallIntegerField(null=True, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
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
        if self.vendor == self.Vendor.SSLCOMMERZ:
            return {
                "vendor": self.vendor,
                "card_type": self.card_type,
                "bank_tran_id": self.bank_tran_id,
                "risk_level": self.risk_level,
            }
        return {"vendor": self.vendor, "sent_from": self.sent_from, "sent_to": self.sent_to}
