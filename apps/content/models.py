from django.db import models

from apps.core.models import TimestampModel


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
