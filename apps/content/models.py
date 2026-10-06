from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import OrderedModel, TimestampModel


class NoticeCategory(TimestampModel, OrderedModel):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_("slug"))
    notice_category = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )

    class Meta:
        ordering = ["order", "title"]
        verbose_name_plural = "notice categories"

    def __str__(self):
        return self.title


class Notice(TimestampModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_("slug"))
    body = models.TextField(blank=True)
    image = models.URLField(null=True, blank=True)
    categories = models.ManyToManyField(NoticeCategory, related_name="notices", blank=True)

    def __str__(self):
        return self.title


class Testimonial(TimestampModel):
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    ratings = models.PositiveSmallIntegerField(default=5)
    image = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.name


class Advertisement(TimestampModel):
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    link = models.URLField(null=True, blank=True)
    type = models.CharField(max_length=50, blank=True)
    image = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.title or f"Advertisement #{self.pk}"


class EBook(TimestampModel):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    booking_link = models.URLField(null=True, blank=True)
    preview = models.URLField(null=True, blank=True)
    image = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.title


class Page(TimestampModel):
    """Fixed-key CMS pages (about-us, terms, privacy, ...) -- seeded once,
    edited (never created/deleted) from the admin panel."""

    class ValueType(models.TextChoices):
        HTML = "html", "HTML"
        IMAGE = "image", "Image"
        COUNTER = "counter", "Counter"

    key = models.SlugField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, blank=True)
    value_type = models.CharField(max_length=20, choices=ValueType.choices, default=ValueType.HTML)
    value = models.TextField(blank=True)
    image = models.URLField(null=True, blank=True)
    video = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.key

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.key
        super().save(*args, **kwargs)
