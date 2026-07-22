from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base adding created_at/updated_at, used by every domain model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class OrderedModel(models.Model):
    """Abstract base for models that expose a manual display `order`."""

    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order"]
