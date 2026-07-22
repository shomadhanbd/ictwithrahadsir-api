from django.db import models

from apps.core.models import OrderedModel, TimeStampedModel


class Teacher(TimeStampedModel, OrderedModel):
    """The "Teachers/Team" roster shown on the admin panel's Teachers page
    and used as the public "founder/instructor" listing on the client site."""

    class Type(models.TextChoices):
        INSTRUCTOR = "instructor", "Instructor"
        FOUNDER = "founder", "Founder"

    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.INSTRUCTOR)
    image = models.URLField(null=True, blank=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name
