from django.conf import settings
from django.db import models

from apps.core.models import OrderedModel, TimestampModel
from apps.core.slugs import ascii_slug


def unique_slugify(model, instance, base_text):
    base_slug = ascii_slug(base_text)
    slug = base_slug
    i = 1
    while model.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        i += 1
        slug = f"{base_slug}-{i}"
    return slug


class NoticeCategory(TimestampModel, OrderedModel):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    notice_category = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )

    class Meta:
        ordering = ["order", "title"]
        verbose_name_plural = "notice categories"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(NoticeCategory, self, self.title)
        super().save(*args, **kwargs)


class Notice(TimestampModel):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    body = models.TextField(blank=True)
    image = models.URLField(null=True, blank=True)
    categories = models.ManyToManyField(NoticeCategory, related_name="notices", blank=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(Notice, self, self.title)
        super().save(*args, **kwargs)


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
