from django.conf import settings
from django.db import models
from django.utils.text import slugify

from apps.core.models import OrderedModel, TimeStampedModel
from apps.courses.models import Course, CoursePrice, CourseCategory


def unique_product_slug(instance, base_text):
    base_slug = slugify(base_text)[:200] or "product"
    slug = base_slug
    i = 1
    while Product.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        i += 1
        slug = f"{base_slug}-{i}"
    return slug


class Product(TimeStampedModel, OrderedModel):
    """Physical/digital items sold outside the course-subscription flow
    (books, ICT Digest, etc.)."""

    class CouponDiscountType(models.TextChoices):
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_till = models.DateTimeField(null=True, blank=True)

    coupon = models.CharField(max_length=50, blank=True)
    coupon_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    coupon_discount_type = models.CharField(
        max_length=20, choices=CouponDiscountType.choices, default=CouponDiscountType.PERCENT
    )
    coupon_valid_till = models.DateTimeField(null=True, blank=True)

    featured = models.BooleanField(default=False)
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    is_book = models.BooleanField(default=True)
    image = models.URLField(null=True, blank=True)
    categories = models.ManyToManyField(CourseCategory, related_name="products", blank=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_product_slug(self, self.name)
        super().save(*args, **kwargs)


class CartItem(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ["user", "product"]

    def __str__(self):
        return f"{self.user} x {self.product} ({self.quantity})"


class Order(TimeStampedModel):
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
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
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


class Payment(TimeStampedModel):
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
    transaction_id = models.CharField(max_length=100)
    vendor = models.CharField(max_length=20, choices=Vendor.choices, default=Vendor.BKASH)
    sent_from = models.CharField(max_length=20, blank=True)
    sent_to = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment for order #{self.order_id}"

    @property
    def details(self):
        return {"vendor": self.vendor, "sent_from": self.sent_from, "sent_to": self.sent_to}
