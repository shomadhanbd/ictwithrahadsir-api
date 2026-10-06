from datetime import datetime, time

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.billing.managers import PaymentQuerySet, ProductQuerySet
from apps.billing.utils import generate_transaction_id
from apps.core.models import TimestampModel
from apps.courses.models import Course


class Product(TimestampModel):
    title = models.CharField("Title", max_length=255)
    description = models.TextField("Description", blank=True)
    product_id = models.SlugField("Product ID", max_length=280, unique=True)
    courses = models.ManyToManyField(Course, related_name="products", verbose_name="Courses")
    price = models.PositiveIntegerField("Price")
    base_price = models.PositiveIntegerField("Base Price")
    # After this, students pay `base_price`; null keeps the discount running.
    discount_ends_at = models.DateTimeField("Discount Ends At", null=True, blank=True)
    access_days = models.PositiveIntegerField("Access Days", null=True, blank=True)
    access_ends_on = models.DateField("Access Ends On", null=True, blank=True)
    is_active = models.BooleanField("Active", default=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        verbose_name = "Product"
        verbose_name_plural = "Products"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(access_days__isnull=True) | models.Q(access_ends_on__isnull=True),
                name="product_access_is_days_or_end_date",
            )
        ]

    def __str__(self):
        return self.title

    @property
    def access_ends_at(self):
        """The end of `access_ends_on`, in the site's time zone."""
        if self.access_ends_on is None:
            return None
        return timezone.make_aware(datetime.combine(self.access_ends_on, time.max))

    @property
    def discount_active(self) -> bool:
        if self.base_price <= self.price:
            return False
        return self.discount_ends_at is None or self.discount_ends_at > timezone.now()

    @property
    def current_price(self) -> int:
        return self.price if self.discount_active else max(self.price, self.base_price)


class Payment(TimestampModel):
    class Status(models.TextChoices):
        INITIATED = "INITIATED", "Initiated"
        VALID = "VALID", "Valid"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"

    class Method(models.TextChoices):
        ONLINE = "online", "Online"
        CASH = "cash", "Cash"

    transaction_id = models.CharField("Transaction ID", max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, related_name="payments", verbose_name="User"
    )
    product = models.ForeignKey(Product, models.PROTECT, related_name="payments", verbose_name="Product")
    amount = models.PositiveIntegerField("Amount")
    # Null means lifetime access.
    access_until = models.DateTimeField("Access Until", null=True, blank=True)
    status = models.CharField("Status", max_length=16, choices=Status.choices, default=Status.INITIATED, db_index=True)
    card_type = models.CharField("Card Type", max_length=64, blank=True)
    card_issuer_country = models.CharField("Card Issuer Country", max_length=64, blank=True)
    transaction_date = models.DateTimeField("Transaction Date", null=True, blank=True)
    gateway_response = models.JSONField("Gateway Response", default=dict, blank=True)
    # The checkout page SSLCommerz opened, handed back if the buyer starts the same checkout again.
    gateway_page_url = models.URLField("Gateway Page", max_length=500, blank=True)
    # Paid for access the buyer already had: no access is granted, and the money is owed back.
    refund_due = models.BooleanField("Refund Due", default=False)
    method = models.CharField("Method", max_length=16, choices=Method.choices, default=Method.ONLINE)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Recorded By"
    )
    note = models.CharField("Note", max_length=255, blank=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(fields=["user", "product"]),
            models.Index(fields=["status", "created_at"]),  # the dashboard's income figures
        ]

    def __str__(self):
        return self.transaction_id

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            candidate = generate_transaction_id(self.product_id)
            while Payment.objects.filter(transaction_id=candidate).exists():
                candidate = generate_transaction_id(self.product_id)
            self.transaction_id = candidate
        super().save(*args, **kwargs)

    @property
    def title(self):
        return self.product.title

    def unlocked_courses(self):
        return list(self.product.courses.all())
