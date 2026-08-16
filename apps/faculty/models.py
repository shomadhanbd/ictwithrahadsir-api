from django.conf import settings
from django.db import models

from apps.core.models import OrderedModel, TimestampModel


class Teacher(TimestampModel, OrderedModel):
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


class CourseInstructor(TimestampModel, OrderedModel):
    """A teacher's assignment to one course, with its commission.

    Was `courses.Instructor`, which duplicated Teacher's name, designation,
    description, type and image with no link between the two -- the seed
    command literally copied the values across. `teacher` is that missing
    link.

    The copied fields survive as per-course overrides: a teacher can be
    billed under a different title on one course. They are filled from the
    linked teacher on save when left blank, so the public payload is
    identical whether or not anyone overrode anything.
    """

    class Type(models.TextChoices):
        INSTRUCTOR = "instructor", "Instructor"
        FOUNDER = "founder", "Founder"

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assignments",
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="instructors",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instructor_profiles",
    )

    # -- per-course overrides, defaulted from `teacher` --
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=150, blank=True)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.INSTRUCTOR)
    image = models.URLField(null=True, blank=True)

    # -- assignment-specific --
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    institute = models.CharField(max_length=255, blank=True)
    commission = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["order", "-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.teacher_id:
            for field in ("name", "designation", "description", "image"):
                if not getattr(self, field):
                    setattr(self, field, getattr(self.teacher, field))
        super().save(*args, **kwargs)
