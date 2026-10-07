from django.conf import settings
from django.db import models

from apps.core.models import TimestampModel
from apps.exam.managers import ExamAttemptQuerySet, ExamQuerySet
from apps.question.models import Question


class Exam(TimestampModel):
    """One paper: its configuration, and the sections it is made of."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class Scope(models.TextChoices):
        STANDALONE = "standalone", "Standalone"
        BATCH = "batch", "Batch"
        COURSE = "course", "Course"

    title = models.CharField("Title", max_length=200)
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

    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.STANDALONE)
    batch = models.ForeignKey(
        "academic.Batch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exams",
    )
    lesson = models.OneToOneField(
        "courses.Content",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="exam",
    )
    # The sum of the sections' marks, kept by `apps.exam.signals`; never typed.
    total_marks = models.DecimalField("Total Marks", max_digits=6, decimal_places=2, default=0, editable=False)
    pass_marks = models.DecimalField("Pass Marks", max_digits=6, decimal_places=2, null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField("Duration", null=True, blank=True)
    start_time = models.DateTimeField("Starts", null=True, blank=True)
    end_time = models.DateTimeField("Ends", null=True, blank=True)
    result_publish_time = models.DateTimeField("Results At", null=True, blank=True)

    max_attempts = models.PositiveSmallIntegerField("Max Attempts", default=1)

    objects = ExamQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "Exam"
        verbose_name_plural = "Exams"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(start_time__isnull=True)
                    | models.Q(end_time__isnull=True)
                    | models.Q(end_time__gt=models.F("start_time"))
                ),
                name="exam_ends_after_it_starts",
            ),
            models.CheckConstraint(condition=models.Q(max_attempts__gte=1), name="exam_allows_one_attempt"),
            models.CheckConstraint(
                condition=(models.Q(scope="course") & models.Q(lesson__isnull=False))
                | (~models.Q(scope="course") & models.Q(lesson__isnull=True)),
                name="exam_course_scope_has_lesson",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "start_time"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["scope"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # `total_marks` is written only by `sync_exam_total`; an instance loaded earlier must not save a stale one.
        if self.pk and not kwargs.get("force_insert") and kwargs.get("update_fields") is None:
            kwargs["update_fields"] = [
                field.name
                for field in self._meta.concrete_fields
                if not field.primary_key and field.name != "total_marks"
            ]
        super().save(*args, **kwargs)

    def clean(self):
        from apps.exam import validators  # validators import this module

        validators.validate_exam(
            pass_marks=self.pass_marks,
            max_attempts=self.max_attempts,
            duration_minutes=self.duration_minutes,
            start_time=self.start_time,
            end_time=self.end_time,
            result_publish_time=self.result_publish_time,
        )
        validators.validate_exam_scope(
            scope=self.scope,
            batch=self.batch if self.batch_id else None,
            lesson=self.lesson if self.lesson_id else None,
        )


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

    # Kept up to date by `apps.exam.signals`.
    question_count = models.PositiveSmallIntegerField("Question Count", default=0)
    computed_marks = models.DecimalField("Computed Marks", max_digits=7, decimal_places=2, default=0)

    class Meta:
        ordering = ["exam_id", "order", "id"]
        verbose_name = "Exam Section"
        verbose_name_plural = "Exam Sections"
        constraints = [
            models.UniqueConstraint(fields=["exam", "title"], name="unique_section_title_per_exam"),
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
        from apps.exam import validators  # validators import this module

        if self.exam_id is None:
            return

        validators.validate_paper_is_editable(self.exam)
        validators.validate_section(
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
        """How many of the offered questions actually count."""
        return self.required_question_count or self.question_count

    @property
    def target_marks(self):
        """What this section's questions should add up to."""
        if self.required_question_count:
            return self.required_question_count * self.marks_per_question
        return self.computed_marks


class ExamSectionQuestion(TimestampModel):
    """One block placed in one section, at a mark and a position."""

    section = models.ForeignKey(ExamSection, on_delete=models.CASCADE, related_name="section_questions")
    block = models.ForeignKey("question.QuestionBlock", on_delete=models.PROTECT, related_name="exam_usages")
    # A passage of many MCQs costs its question count at the rate, so this outgrows two integer digits.
    marks = models.DecimalField("Marks", max_digits=6, decimal_places=2, default=1)
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
        """Remembers the section this pick was loaded from, for the total signals."""
        instance = super().from_db(db, field_names, values, fetch_mode=fetch_mode)
        if "section_id" in field_names:
            instance._section_on_load = instance.section_id
        return instance

    def clean(self):
        from apps.exam import validators  # validators import this module

        if self.section_id is None or self.block_id is None:
            return
        validators.validate_paper_is_editable(self.section.exam)
        validators.validate_section_blocks(section=self.section, blocks=[self.block])
        validators.validate_pick_marks(section=self.section, block=self.block, marks=self.marks)


class ExamAttempt(TimestampModel):
    """One student's sitting of one exam."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"

    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_attempts")
    number = models.PositiveSmallIntegerField(default=1)
    seed = models.BigIntegerField()
    started_at = models.DateTimeField()
    # The duration from the start, capped by the exam's end time.
    deadline = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)

    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    correct = models.PositiveSmallIntegerField(default=0)
    wrong = models.PositiveSmallIntegerField(default=0)
    skipped = models.PositiveSmallIntegerField(default=0)
    # The first submitted attempt; the one that is ranked.
    is_official = models.BooleanField(default=False)
    # A written (CQ) answer is waiting for a teacher; the score so far is only the auto-marked part.
    awaiting_marking = models.BooleanField(default=False)
    # Section rates frozen at the start: {section_id: {"positive": .., "negative": ..}}.
    marking = models.JSONField(default=dict)

    objects = ExamAttemptQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["exam", "user", "number"], name="unique_attempt_number"),
            # The ranked attempt is the first submitted one; the database holds that whatever path submits.
            models.UniqueConstraint(
                fields=["exam", "user"], condition=models.Q(is_official=True), name="one_official_attempt_per_exam"
            ),
        ]
        indexes = [
            models.Index(fields=["exam", "is_official", "score"]),
            models.Index(fields=["user", "exam"]),
            models.Index(fields=["status", "deadline"]),  # the every-minute finalize_exam_attempts query
        ]

    def __str__(self):
        return f"{self.user} on {self.exam} (#{self.number})"

    @property
    def time_taken(self):
        if not self.submitted_at:
            return None
        return self.submitted_at - self.started_at

    @property
    def time_taken_seconds(self) -> int | None:
        return int(self.time_taken.total_seconds()) if self.time_taken else None


class ExamAnswer(TimestampModel):
    """What a student chose for one question of one attempt."""

    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="answers")
    section_question = models.ForeignKey(ExamSectionQuestion, on_delete=models.PROTECT, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="exam_answers")
    selected_option_ids = models.JSONField(default=list)
    is_correct = models.BooleanField(null=True, blank=True)
    marks_awarded = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    # Set when a teacher marks a written (CQ) part; auto-marked answers leave them empty.
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="unique_answer_per_question"),
        ]

    def __str__(self):
        return f"{self.attempt} — Q{self.question_id}"


class ExamAnswerSheet(TimestampModel):
    """The photos or PDF of a student's handwritten answer to one creative question on their paper."""

    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="sheets")
    section_question = models.ForeignKey(ExamSectionQuestion, on_delete=models.PROTECT, related_name="answer_sheets")
    # [{"link": url, "name": original file name, "kind": "image" | "pdf"}], in upload order.
    files = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "section_question"], name="unique_sheet_per_question"),
        ]

    def __str__(self):
        return f"{self.attempt} — sheet for pick {self.section_question_id}"
