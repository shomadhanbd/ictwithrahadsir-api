from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import TimestampModel


class Feedback(TimestampModel):
    """A rating and comment; students write their own, staff may add one they received elsewhere."""

    class Source(models.TextChoices):
        COURSE = "course", "Course"
        GENERAL = "general", "General"

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for approval"
        APPROVED = "approved", "Approved"
        HIDDEN = "hidden", "Hidden"

    source = models.CharField(max_length=20, choices=Source.choices)
    course = models.ForeignKey(
        "courses.Course", null=True, blank=True, on_delete=models.CASCADE, related_name="feedback"
    )
    # Empty when staff typed it.
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback"
    )
    # Shown on the site; copied from the student, editable by staff.
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=150, blank=True)
    image = models.URLField(blank=True)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Shown on the home page.
    is_featured = models.BooleanField(default=False)

    class Meta(TimestampModel.Meta):
        verbose_name_plural = "feedback"
        indexes = [models.Index(fields=["source", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source="course", course__isnull=False)
                | (~models.Q(source="course") & models.Q(course__isnull=True)),
                name="feedback_course_matches_source",
            ),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="feedback_rating_1_to_5"),
            models.CheckConstraint(
                condition=~models.Q(is_featured=True) | models.Q(status="approved"),
                name="feedback_featured_is_approved",
            ),
            models.UniqueConstraint(
                fields=["author", "course"], condition=models.Q(source="course"), name="feedback_one_per_course"
            ),
            models.UniqueConstraint(
                fields=["author"], condition=models.Q(source="general"), name="feedback_one_general"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.rating}★, {self.get_source_display()})"
