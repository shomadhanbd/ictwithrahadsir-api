"""Physical and digital goods sold alongside the courses.

Separate from `billing`: this is the catalogue and the basket, while
billing owns the money. `billing.Order` points here for a product
purchase, so the dependency runs billing -> store, never back.
"""

from django.conf import settings
from django.db import models

from apps.core.models import OrderedModel, TimestampModel
from apps.core.slugs import unique_slug
from apps.courses.models import CourseCategory
from apps.store.managers import CartItemQuerySet, ProductQuerySet


class Product(TimestampModel, OrderedModel):
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

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name, fallback="product")
        super().save(*args, **kwargs)


class CartItem(TimestampModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)

    objects = CartItemQuerySet.as_manager()

    class Meta:
        unique_together = ["user", "product"]

    def __str__(self):
        return f"{self.user} x {self.product} ({self.quantity})"
