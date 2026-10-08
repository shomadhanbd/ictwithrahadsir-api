from django.db import models

from apps.core.models import OrderedModel, TimestampModel


class MaterialCategory(TimestampModel, OrderedModel):
    name = models.CharField(max_length=100, unique=True)
    # A lucide icon name.
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name_plural = "Material categories"

    def __str__(self):
        return self.name


class MaterialTopic(TimestampModel, OrderedModel):
    class Access(models.TextChoices):
        FREE = "free", "Free for everyone"
        ENROLLED = "enrolled", "Students of chosen courses"

    category = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, related_name="topics")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    cover = models.URLField(blank=True)
    class_level = models.ForeignKey(
        "academic.ClassLevel", null=True, blank=True, on_delete=models.SET_NULL, related_name="material_topics"
    )
    group = models.ForeignKey(
        "academic.Group", null=True, blank=True, on_delete=models.SET_NULL, related_name="material_topics"
    )
    access = models.CharField(max_length=20, choices=Access.choices, default=Access.FREE)
    # With ENROLLED access, a current enrolment in any of these opens the topic.
    courses = models.ManyToManyField("courses.Course", blank=True, related_name="material_topics")
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "-id"]

    def __str__(self):
        return self.title


class MaterialItem(TimestampModel, OrderedModel):
    class Kind(models.TextChoices):
        PDF = "pdf", "PDF"
        VIDEO = "video", "YouTube video"
        LINK = "link", "Link"
        BOOK = "book", "Book"

    topic = models.ForeignKey(MaterialTopic, on_delete=models.CASCADE, related_name="items")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=500, blank=True)
    image = models.URLField(blank=True)
    preview_url = models.URLField(max_length=500, blank=True)
    # Books only, in taka; delivery is added at checkout.
    price = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class DeliveryRate(TimestampModel):
    class Zone(models.TextChoices):
        SYLHET = "sylhet", "Inside Sylhet"
        OUTSIDE = "outside", "Outside Sylhet"

    zone = models.CharField(max_length=20, choices=Zone.choices, unique=True)
    charge = models.PositiveIntegerField()

    class Meta:
        ordering = ["-zone"]

    def __str__(self):
        return f"{self.get_zone_display()}: {self.charge}"


class BookOrder(TimestampModel):
    """Counts once its payment is VALID; deleted with a payment the gateway refused."""

    payment = models.OneToOneField("billing.Payment", on_delete=models.CASCADE, related_name="book_order")
    item = models.ForeignKey(MaterialItem, null=True, on_delete=models.SET_NULL, related_name="orders")
    # Kept from the item, which may be removed later.
    title = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    address = models.TextField()
    zone = models.CharField(max_length=20, choices=DeliveryRate.Zone.choices)
    book_price = models.PositiveIntegerField()
    delivery_charge = models.PositiveIntegerField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} → {self.name}"
