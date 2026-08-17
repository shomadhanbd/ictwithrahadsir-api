from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import OrderedModel, TimestampModel
from apps.core.slugs import unique_slug


class CourseCategory(TimestampModel, OrderedModel):
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    image = models.URLField(null=True, blank=True)
    category = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )

    class Meta:
        ordering = ["order", "title"]
        verbose_name_plural = "course categories"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*args, **kwargs)


class Course(TimestampModel):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    is_online = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    fake_user_count = models.PositiveIntegerField(default=0)

    description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)
    video = models.URLField(null=True, blank=True)
    pdf_link = models.URLField(null=True, blank=True)
    image = models.URLField(null=True, blank=True)

    categories = models.ManyToManyField(CourseCategory, related_name="courses", blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Every public listing filters on active, and the homepage adds
            # featured. Both are low-cardinality on their own but the pair
            # selects the small set the catalogue actually serves.
            models.Index(fields=["active", "featured"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*args, **kwargs)

    @property
    def video_count(self):
        return self.contents.filter(type=Content.Type.VIDEO).count()

    @property
    def pdf_count(self):
        return self.contents.filter(type=Content.Type.PDF).count()

    @property
    def exam_count(self):
        return self.contents.filter(type=Content.Type.EXAM).count()

    @property
    def note_count(self):
        return self.contents.filter(type=Content.Type.NOTE).count()

    @property
    def link_count(self):
        return self.contents.filter(type=Content.Type.LINK).count()

    @property
    def live_count(self):
        return self.contents.filter(type=Content.Type.LIVE).count()

    @property
    def class_count(self):
        return self.contents.count()

    @property
    def prices(self):
        """CoursePrice attaches polymorphically (`priceable_type`/`priceable_id`,
        matching the admin panel's real payload), not via a direct FK -- this
        keeps `course.prices.filter(...)/.order_by(...)/.first()` working the
        same way it would with a normal reverse FK manager."""
        return CoursePrice.objects.filter(priceable_type=CoursePrice.PRICEABLE_COURSE, priceable_id=self.id)


class CoursePrice(TimestampModel):
    PRICEABLE_COURSE = "course"
    PRICEABLE_TYPE_CHOICES = [
        (PRICEABLE_COURSE, "Course"),
    ]

    class Type(models.TextChoices):
        FULL = "full", "Full"
        PARTIAL = "partial", "Partial"
        SUBSCRIPTION = "subscription", "Subscription"

    class ValidityType(models.TextChoices):
        ABSOLUTE = "absolute", "Absolute"
        RELATIVE = "relative", "Relative"

    priceable_type = models.CharField(
        max_length=50, choices=PRICEABLE_TYPE_CHOICES, default=PRICEABLE_COURSE
    )
    priceable_id = models.PositiveIntegerField()
    title = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_till = models.DateTimeField(null=True, blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.FULL)
    validity_type = models.CharField(
        max_length=20, choices=ValidityType.choices, default=ValidityType.RELATIVE
    )
    validity_time = models.DateTimeField(null=True, blank=True)
    validity_duration = models.PositiveIntegerField(
        null=True, blank=True, help_text="Validity length in days (relative validity)"
    )

    class Meta:
        ordering = ["amount"]
        indexes = [models.Index(fields=["priceable_type", "priceable_id"])]

    def __str__(self):
        return f"{self.priceable_type}#{self.priceable_id} - {self.title}"

    @property
    def course(self):
        """Convenience accessor -- `course` is the only priceable type today."""
        if self.priceable_type != self.PRICEABLE_COURSE:
            return None
        return Course.objects.filter(pk=self.priceable_id).first()


class Coupon(TimestampModel):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    price = models.ForeignKey(CoursePrice, on_delete=models.CASCADE, related_name="coupons")
    code = models.CharField(max_length=50)
    discount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(
        max_length=20, choices=DiscountType.choices, default=DiscountType.PERCENT
    )
    valid_till = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["price", "code"]

    def __str__(self):
        return self.code


class Routine(TimestampModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="routines")
    title = models.CharField(max_length=150)
    link = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.title


class Section(TimestampModel, OrderedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    section = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="sub_sections"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            # The course detail page pulls a course's whole active section
            # tree in one go.
            models.Index(fields=["course", "active"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, f"{self.course_id}-{self.title}")
        super().save(*args, **kwargs)


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
        DRAFT = "Draft", "Draft"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="contents")
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="contents")
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    type = models.CharField(max_length=20, choices=Type.choices)
    variant = models.CharField(max_length=20, choices=Variant.choices, default=Variant.NEW)
    available_from = models.DateTimeField(null=True, blank=True)
    paid = models.BooleanField(default=True)
    active = models.BooleanField(default=True)

    # -- video --
    video_source = models.CharField(max_length=20, default="youtube", blank=True)
    video_link = models.URLField(null=True, blank=True)
    video_description = models.TextField(blank=True)
    video_embedded = models.BooleanField(default=True)
    video_cipher = models.BooleanField(default=False)

    # -- note --
    note_body = models.TextField(blank=True)

    # -- pdf --
    pdf_file = models.URLField(null=True, blank=True)

    # -- link --
    link_url = models.URLField(null=True, blank=True)

    # -- live --
    live_url = models.URLField(null=True, blank=True)
    live_scheduled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            # The per-type totals on every course payload group by exactly
            # this pair, over every course on the page.
            models.Index(fields=["course", "type"]),
            # The section tree loads a course's active contents in one query.
            models.Index(fields=["course", "active"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def is_accessible_by(self, user) -> bool:
        """Whether `user` may open this content.

        Free content is open to everyone; paid content needs a current
        enrolment on the owning course. Lives on the model rather than in
        `courses` views because `exams` needs the same rule and used to
        import a private helper out of another app's view module.
        """
        if not self.paid:
            return True
        if not user or not user.is_authenticated:
            return False

        enrollment = Enrollment.objects.filter(course_id=self.course_id, user=user).first()
        if not enrollment:
            return False
        if enrollment.valid_till and enrollment.valid_till < timezone.now():
            return False
        return True


class ContentCompletion(TimestampModel):
    """One row per lesson a student has finished.

    There was no progress anywhere in the schema, so the course player could
    not answer "how far am I?" without inventing a number — it fell back to
    remembering the last lesson opened in the browser's own storage, which is
    per-device and vanishes with a cache clear.

    Completion rather than a percentage per lesson: a lesson is watched or it
    is not, and a course's progress is then a count over its contents, which
    stays correct when contents are added or removed. `course` is denormalised
    off the content so the common query — this user's completions on this
    course — is a single indexed lookup instead of a join through Content.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_completions",
    )
    content = models.ForeignKey(
        Content, on_delete=models.CASCADE, related_name="completions"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="content_completions"
    )
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ["user", "content"]
        indexes = [models.Index(fields=["user", "course"])]

    def __str__(self):
        return f"{self.user} finished {self.content}"

    def save(self, *args, **kwargs):
        # The course is always the content's course; taking it from the caller
        # would let the two drift apart.
        if self.content_id and self.course_id != self.content.course_id:
            self.course_id = self.content.course_id
        super().save(*args, **kwargs)


class Enrollment(TimestampModel):
    """Enrollment pivot -- who has access to which course, until when, and
    how they got it."""

    class PaymentType(models.TextChoices):
        FREE = "free", "Free"
        PAID = "paid", "Paid"
        SUBSCRIPTION = "subscription", "Subscription"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_enrollments"
    )
    valid_till = models.DateTimeField(null=True, blank=True)
    payment_type = models.CharField(
        max_length=20, choices=PaymentType.choices, default=PaymentType.FREE
    )

    class Meta:
        unique_together = ["course", "user"]

    def __str__(self):
        return f"{self.user} -> {self.course}"


class CourseMaterial(TimestampModel):
    """A supplementary file hung off a course.

    Lived in `cms` despite being course-shaped; it duplicates what a
    Content of type pdf/note models, minus the section tree and access
    control.
    """

    title = models.CharField(max_length=255)
    type = models.CharField(max_length=50, blank=True)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="materials", null=True, blank=True
    )
    file = models.URLField(null=True, blank=True)

    def __str__(self):
        return self.title
