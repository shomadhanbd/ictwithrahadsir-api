"""Exam authoring: a paper assembled out of the question bank.

An exam is ordered `ExamSection`s, each holding `question.QuestionBlock`s. A
block is already "one item" -- a standalone question, or a stimulus (উদ্দীপক)
with its ক/খ/গ/ঘ parts -- so a 30-block MCQ section and a 7-block CQ section are
the same shape.

**Authoring only.** Nothing here records an attempt, an answer or a mark earned.

`apps.exam.Exam` is not `apps.assessment.Exam`, and `apps.question.Question` is
not `apps.assessment.Question`. The two systems are parallel and share nothing;
any module importing both must alias.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimestampModel
from apps.core.slugs import BanglaSlugField, unique_slug
from apps.question.models import Question


class Exam(TimestampModel):
    """One paper: its configuration, and the sections it is made of.

    Carries no "paper type" of its own -- what a paper contains is the set of
    its sections' types, declared where the sections are.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Scope(models.TextChoices):
        STANDALONE = "standalone", "Standalone"
        BATCH = "batch", "Batch"

    title = models.CharField("Title", max_length=200)
    slug = BanglaSlugField("Slug", max_length=220, unique=True, blank=True)
    description = models.TextField("Description", blank=True)
    instructions = models.TextField("Instructions", blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_exams",
        editable=False,
    )

    # -- scope: the discriminator plus one nullable column per scope ---------
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.STANDALONE)
    batch = models.ForeignKey(
        "academic.Batch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exams",
    )
    # -- configuration ------------------------------------------------------
    total_marks = models.DecimalField("Total Marks", max_digits=6, decimal_places=2, default=100)
    pass_marks = models.DecimalField("Pass Marks", max_digits=6, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField("Duration", null=True, blank=True)
    start_time = models.DateTimeField("Starts", null=True, blank=True)
    end_time = models.DateTimeField("Ends", null=True, blank=True)
    result_publish_time = models.DateTimeField("Results At", null=True, blank=True)

    max_attempts = models.PositiveSmallIntegerField("Max Attempts", default=1)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "Exam"
        verbose_name_plural = "Exams"
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(pass_marks__isnull=True) | models.Q(pass_marks__lte=models.F("total_marks"))),
                name="exam_pass_marks_within_total",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(start_time__isnull=True)
                    | models.Q(end_time__isnull=True)
                    | models.Q(end_time__gt=models.F("start_time"))
                ),
                name="exam_ends_after_it_starts",
            ),
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1), name="exam_allows_one_attempt"),
        ]
        indexes = [
            models.Index(fields=["status", "start_time"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["scope"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        # Imported here, not at module scope: `services` imports this module.
        from apps.exam import services

        services.validate_exam(
            total_marks=self.total_marks,
            pass_marks=self.pass_marks,
            max_attempts=self.max_attempts,
            duration_minutes=self.duration_minutes,
            start_time=self.start_time,
            end_time=self.end_time,
            result_publish_time=self.result_publish_time,
        )
        services.validate_exam_scope(
            scope=self.scope,
            batch=self.batch if self.batch_id else None,
        )

    def save(self, *args, **kwargs):
        if not self.slug:
            # Bangla titles transliterate; see `apps.core.slugs`.
            self.slug = unique_slug(self, self.title)
        super().save(*args, **kwargs)


class ExamSection(TimestampModel):
    """One part of a paper: "MCQ" worth 30, "সৃজনশীল" worth 70."""

    Type = Question.Type

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField("Title", max_length=150)
    question_type = models.CharField(max_length=20, choices=Type.choices, default=Type.MCQ)

    subject = models.ForeignKey("academic.Subject", on_delete=models.PROTECT, related_name="exam_sections")

    marks = models.DecimalField("Marks", max_digits=6, decimal_places=2, default=0)
    marks_per_question = models.DecimalField("Marks Per Question", max_digits=4, decimal_places=2, default=1)
    negative_marks = models.DecimalField("Marks Per Wrong", max_digits=4, decimal_places=2, null=True, blank=True)
    pass_marks = models.DecimalField("Pass Marks", max_digits=6, decimal_places=2, null=True, blank=True)
    required_question_count = models.PositiveSmallIntegerField("Answers Required", null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField("Duration", null=True, blank=True)
    instructions = models.TextField("Instructions", blank=True)
    order = models.PositiveSmallIntegerField("Order", default=0)

    shuffle_questions = models.BooleanField("Shuffle Questions", default=False)
    shuffle_options = models.BooleanField("Shuffle Options", default=False)

    blocks = models.ManyToManyField(
        "question.QuestionBlock",
        through="ExamSectionQuestion",
        through_fields=("section", "block"),
        related_name="exam_sections",
        blank=True,
    )

    #: Denormalized, maintained by `apps.exam.signals`.
    question_count = models.PositiveSmallIntegerField("Question Count", default=0)
    computed_marks = models.DecimalField("Computed Marks", max_digits=7, decimal_places=2, default=0)

    class Meta:
        ordering = ["exam_id", "order", "id"]
        verbose_name = "Exam Section"
        verbose_name_plural = "Exam Sections"
        constraints = [
            models.UniqueConstraint(fields=["exam", "title"], name="unique_section_title_per_exam"),
            # The `__isnull` branch is not decoration: `NULL <= x` is NULL and
            # a CHECK passes on NULL, so spelling it out says what is meant.
            models.CheckConstraint(
                condition=(
                    models.Q(negative_marks__isnull=True)
                    | (models.Q(negative_marks__gte=0) & models.Q(negative_marks__lte=models.F("marks_per_question")))
                ),
                name="exam_section_negative_marks_within_rate",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(pass_marks__isnull=True)
                    | (models.Q(pass_marks__gt=0) & models.Q(pass_marks__lte=models.F("marks")))
                ),
                name="exam_section_pass_marks_within_marks",
            ),
        ]
        indexes = [
            models.Index(fields=["exam", "order"]),
            models.Index(fields=["question_type"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_question_type_display()})"

    def clean(self):
        # Imported here, not at module scope: `services` imports this module.
        from apps.exam import services

        if self.exam_id is None:
            # A blank admin inline row has no exam to check against yet.
            return

        # The admin is the one door the API's freeze does not cover.
        services.validate_paper_is_editable(self.exam)
        services.validate_section(
            exam=self.exam,
            question_type=self.question_type,
            subject=self.subject if self.subject_id else None,
            marks=self.marks,
            marks_per_question=self.marks_per_question,
            duration_minutes=self.duration_minutes,
            required_question_count=self.required_question_count,
            negative_marks=self.negative_marks,
            pass_marks=self.pass_marks,
            shuffle_options=self.shuffle_options,
            instance=self,
        )

    @property
    def answers_required(self):
        """How many of the offered questions actually count.

        A section with no "answer any N of M" rule requires all of them.
        """
        return self.required_question_count or self.question_count

    @property
    def target_marks(self):
        """What this section's questions should add up to.

        `required_question_count` is the whole reason this is not just
        `computed_marks`: an "answer any 7 of 11" section offers 110 marks of
        questions and is worth 70.
        """
        if self.required_question_count:
            return self.required_question_count * self.marks_per_question
        return self.computed_marks


class ExamSectionQuestion(TimestampModel):
    """One block placed in one section, at a mark and a position.

    The through model for `ExamSection.blocks`. It exists because the paper's
    order and each question's price live on the *placement*, not on the block.
    """

    section = models.ForeignKey(ExamSection, on_delete=models.CASCADE, related_name="section_questions")
    block = models.ForeignKey("question.QuestionBlock", on_delete=models.PROTECT, related_name="exam_usages")
    marks = models.DecimalField("Marks", max_digits=4, decimal_places=2, default=1)
    order = models.PositiveSmallIntegerField("Order", default=0)

    class Meta:
        ordering = ["section_id", "order", "id"]
        verbose_name = "Exam Question"
        verbose_name_plural = "Exam Questions"
        constraints = [models.UniqueConstraint(fields=["section", "block"], name="unique_block_per_exam_section")]
        indexes = [
            models.Index(fields=["section", "order"]),
            models.Index(fields=["block"]),
        ]

    def __str__(self):
        return f"Block #{self.block_id} in {self.section_id}"

    @classmethod
    def from_db(cls, db, field_names, values, *, fetch_mode=None):
        """Remember which section this pick was loaded from.

        A pick moved to another section leaves the old section's counters one
        too high, and `post_save` only ever sees the new one.

        `fetch_mode` is passed straight through: Django 6.1 hands it to every
        `from_db`, and an override that swallows it is an error in 7.0.
        """
        instance = super().from_db(db, field_names, values, fetch_mode=fetch_mode)
        if "section_id" in field_names:
            instance._section_on_load = instance.section_id
        return instance
