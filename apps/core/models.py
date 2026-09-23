from django.db import models


class TimestampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class OrderedModel(models.Model):
    """Adds a manual display `order`."""

    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order"]
