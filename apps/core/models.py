from django.db import models

from apps.core.slugs import unique_slug


class TimestampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class OrderedModel(models.Model):
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order"]


class NameSlugMixin:
    """Fills a blank `slug` from `slug_base()` on save."""

    def slug_base(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.slug_base())
        super().save(*args, **kwargs)


class PkSlugMixin:
    """Fills a blank `slug` with `<slug_prefix>-<pk>` once the row exists."""

    slug_prefix = ""

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.slug:
            self.slug = f"{self.slug_prefix}-{self.pk}"
            super().save(update_fields=["slug"])
