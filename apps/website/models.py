from django.db import models

from apps.core.models import OrderedModel, TimestampModel


class Section(TimestampModel):
    """An edited part of the website; one without a row shows its registry defaults (`registry/`)."""

    key = models.CharField(max_length=100, unique=True)
    is_visible = models.BooleanField(default=True)
    content = models.JSONField(default=dict)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class Banner(TimestampModel, OrderedModel):
    """A slide in the home page's hero carousel."""

    title = models.CharField(max_length=255)
    image = models.URLField(max_length=500)
    link = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    # Shown only between these, when set.
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title
