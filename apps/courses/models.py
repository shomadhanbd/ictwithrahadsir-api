from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import OrderedModel, TimestampModel
from apps.courses.managers import ActiveQuerySet, CourseQuerySet, EnrollmentQuerySet
from apps.courses.validators import (
    course_errors,
    validate_faqs,
    validate_highlights,
    validate_learning_outcomes,
    validate_titles,
)


class Course(TimestampModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    class Delivery(models.TextChoices):
        LIVE = "live", "Live"
        RECORDED = "recorded", "Recorded"
        HYBRID = "hybrid", "Live + recorded"

    class Language(models.TextChoices):
        BANGLA = "bn", "Bangla"
        ENGLISH = "en", "English"
        MIXED = "mixed", "Bangla & English"

    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_("slug"))
    summary = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    is_featured = models.BooleanField(default=False)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, blank=True)
    delivery = models.CharField(max_length=20, choices=Delivery.choices, default=Delivery.RECORDED)
    is_online = models.BooleanField(default=True)
    language = models.CharField(max_length=10, choices=Language.choices, default=Language.BANGLA)
    duration = models.CharField(max_length=100, blank=True)
    # Added to the real enrolment count shown to students.
    fake_student_count = models.PositiveIntegerField(default=0)

    class_level = models.ForeignKey(
        "academic.ClassLevel", null=True, blank=True, on_delete=models.PROTECT, related_name="courses"
    )
    group = models.ForeignKey("academic.Group", null=True, blank=True, on_delete=models.PROTECT, related_name="courses")
    batch = models.ForeignKey("academic.Batch", null=True, blank=True, on_delete=models.PROTECT, related_name="courses")

    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    enrollment_deadline = models.DateTimeField(null=True, blank=True)
    schedule_note = models.CharField(max_length=255, blank=True)

    thumbnail = models.URLField(null=True, blank=True)
    banner = models.URLField(null=True, blank=True)
    promo_video = models.URLField(null=True, blank=True)
    syllabus_pdf = models.URLField(null=True, blank=True)

    learning_outcomes = models.JSONField(default=list, blank=True, validators=[validate_learning_outcomes])
    target_audience = models.JSONField(default=list, blank=True, validators=[validate_titles])
    requirements = models.JSONField(default=list, blank=True, validators=[validate_titles])
    highlights = models.JSONField(default=list, blank=True, validators=[validate_highlights])
    faqs = models.JSONField(default=list, blank=True, validators=[validate_faqs])

    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)
    og_image = models.URLField(null=True, blank=True)

    objects = CourseQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "is_featured"])]

    def __str__(self):
        return self.title

    def clean(self):
        errors = course_errors(
            class_level=self.class_level,
            group=self.group,
            batch=self.batch,
            starts_on=self.starts_on,
            ends_on=self.ends_on,
        )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "published_at"}
        super().save(*args, **kwargs)

    @property
    def enrollment_open(self) -> bool:
        return self.enrollment_deadline is None or self.enrollment_deadline >= timezone.now()

    @property
    def seo(self) -> dict:
        return {
            "title": self.meta_title or self.title,
            "description": self.meta_description or self.summary or self.subtitle,
            "image": self.og_image or self.banner or self.thumbnail,
        }


class Routine(TimestampModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="routines")
    title = models.CharField(max_length=150)
    link = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.title


class Section(TimestampModel, OrderedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    section = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="sub_sections")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_("slug"))
    active = models.BooleanField(default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["course", "active"])]

    def __str__(self):
        return self.title


class Content(TimestampModel, OrderedModel):
    class Type(models.TextChoices):
        VIDEO = "video", "Video"
        NOTE = "note", "Note"
        PDF = "pdf", "PDF"
        EXAM = "exam", "Exam"
        LINK = "link", "Link"
        LIVE = "live", "Live"

    class Variant(models.TextChoices):
        NEW = "New", "New"
        UPDATE = "Update", "Update"
        REVISION = "Revision", "Revision"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="contents")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="contents")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, verbose_name=_("slug"))
    type = models.CharField(max_length=20, choices=Type.choices)
    variant = models.CharField(max_length=20, choices=Variant.choices, default=Variant.NEW)
    available_from = models.DateTimeField(null=True, blank=True)
    paid = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    video_source = models.CharField(max_length=20, default="youtube", blank=True)
    video_link = models.URLField(null=True, blank=True)
    video_description = models.TextField(blank=True)
    video_embedded = models.BooleanField(default=True)
    video_cipher = models.BooleanField(default=False)

    note_body = models.TextField(blank=True)

    pdf_file = models.URLField(null=True, blank=True)

    link_url = models.URLField(null=True, blank=True)

    live_url = models.URLField(null=True, blank=True)
    live_scheduled_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["course", "type"]),
            models.Index(fields=["course", "active"]),
        ]

    def __str__(self):
        return self.title


class ContentCompletion(TimestampModel):
    """A lesson a student has finished."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_completions",
    )
    content = models.ForeignKey(Content, on_delete=models.CASCADE, related_name="completions")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="content_completions")
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ["user", "content"]
        indexes = [models.Index(fields=["user", "course"])]

    def __str__(self):
        return f"{self.user} finished {self.content}"

    def save(self, *args, **kwargs):
        # Denormalised from the lesson; the `courses` signal re-syncs when a lesson moves.
        if self.content_id and self.course_id != self.content.course_id:
            self.course_id = self.content.course_id
        super().save(*args, **kwargs)


class Enrollment(TimestampModel):
    """Who has access to which course, until when, and how they got it."""

    class PaymentType(models.TextChoices):
        FREE = "free", "Free"
        PAID = "paid", "Paid"
        SUBSCRIPTION = "subscription", "Subscription"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_enrollments")
    valid_till = models.DateTimeField(null=True, blank=True)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.FREE)
    # The `valid_till` the student was last reminded about.
    expiry_reminded_for = models.DateTimeField(null=True, blank=True)

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        unique_together = ["course", "user"]
        # The expiry-reminder cron and current-access filters range over it.
        indexes = [models.Index(fields=["valid_till"])]

    def __str__(self):
        return f"{self.user} -> {self.course}"

    @property
    def is_current(self) -> bool:
        return self.valid_till is None or self.valid_till >= timezone.now()  # as `current_q`

    @property
    def status(self) -> str:
        return "active" if self.is_current else "expired"


class CourseMaterial(TimestampModel):
    """A supplementary file for a course, such as a lecture sheet."""

    title = models.CharField(max_length=255)
    type = models.CharField(max_length=50, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials", null=True, blank=True)
    file = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.title


class CourseTeacher(TimestampModel, OrderedModel):
    """A teacher's assignment to one course, with their commission."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="instructors")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teaching")
    commission = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=(
            "Percent of each sale of this course paid to this teacher. "
            "Recorded only -- nothing computes a payout from it yet."
        ),
    )

    class Meta:
        ordering = ["order", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["course", "user"], name="unique_teacher_per_course")]

    def __str__(self):
        return f"{self.user} on {self.course}"
