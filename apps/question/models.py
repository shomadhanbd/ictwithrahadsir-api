from django.db import models

from apps.core.models import TimestampModel


class QuestionSource(TimestampModel):
    """One exam a question appeared in: ঢাকা বোর্ড ২০১৯, ঢাবি ক-ইউনিট ২০২১."""

    class Kind(models.TextChoices):
        BOARD = "board", "Board"
        COLLEGE = "college", "College"
        UNIVERSITY = "university", "University"
        SCHOOL = "school", "School"
        OTHER = "other", "Other"

    kind = models.CharField("Kind", max_length=20, choices=Kind.choices, default=Kind.BOARD)
    name = models.CharField("Name", max_length=150)
    year = models.PositiveSmallIntegerField("Year", null=True, blank=True)
    unit = models.CharField("Unit", max_length=20, blank=True)
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        ordering = [models.F("year").desc(nulls_last=True), "kind", "name"]
        verbose_name = "Question Source"
        verbose_name_plural = "Question Sources"
        constraints = [
            models.UniqueConstraint(fields=["kind", "name", "year", "unit"], name="unique_question_source"),
            models.UniqueConstraint(
                fields=["kind", "name", "unit"],
                condition=models.Q(year__isnull=True),
                name="unique_undated_question_source",
            ),
        ]
        indexes = [models.Index(fields=["kind", "year"])]

    def __str__(self):
        return self.label

    @property
    def label(self):
        parts = [self.name]
        if self.unit:
            parts.append(f"{self.unit} unit")
        if self.year:
            parts.append(str(self.year))
        return " ".join(parts)


class QuestionBlock(TimestampModel):
    """One item in a chapter feed: a standalone question, or a stimulus group."""

    class Kind(models.TextChoices):
        STANDALONE = "standalone", "Standalone"
        GROUP = "group", "Group"

    subject = models.ForeignKey(
        "academic.Subject",
        on_delete=models.PROTECT,
        related_name="question_blocks",
        verbose_name="Subject",
    )
    chapter = models.ForeignKey(
        "academic.Chapter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="question_blocks",
        verbose_name="Chapter",
    )
    topics = models.ManyToManyField("academic.Topic", blank=True, related_name="question_blocks")

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.STANDALONE)
    order_in_chapter = models.PositiveSmallIntegerField("Order In Chapter", default=0)
    question_count = models.PositiveSmallIntegerField("Question Count", default=0)

    sources = models.ManyToManyField(QuestionSource, blank=True, related_name="question_blocks")

    is_active = models.BooleanField("Active", default=True)

    class Meta:
        ordering = ["order_in_chapter", "id"]
        verbose_name = "Question Block"
        verbose_name_plural = "Question Blocks"
        indexes = [
            models.Index(fields=["subject", "chapter"]),
            models.Index(fields=["chapter", "order_in_chapter"]),
            models.Index(fields=["kind"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} block #{self.pk}"


class QuestionSet(TimestampModel):
    """The shared stimulus of a group block."""

    class StimulusType(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        TABLE = "table", "Table"
        DIAGRAM = "diagram", "Diagram"
        CODE = "code", "Code"
        COMPOSITE = "composite", "Composite"

    block = models.OneToOneField(QuestionBlock, on_delete=models.CASCADE, related_name="question_set")
    stimulus_type = models.CharField(max_length=20, choices=StimulusType.choices, blank=True)
    stimulus_content = models.TextField("Stimulus")

    class Meta:
        verbose_name = "Question Set"
        verbose_name_plural = "Question Sets"

    def __str__(self):
        return f"Stimulus #{self.pk}"

    def clean(self):
        from apps.question.validators import validate_set_block  # validators import this module

        validate_set_block(self.block if self.block_id else None)


class Question(TimestampModel):
    """One question, owned by either a block or a set -- never both, never neither."""

    class Type(models.TextChoices):
        MCQ = "mcq", "MCQ"
        CQ = "cq", "Creative Question"

    block = models.OneToOneField(
        QuestionBlock,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="standalone_question",
    )
    question_set = models.ForeignKey(
        QuestionSet, on_delete=models.CASCADE, null=True, blank=True, related_name="questions"
    )

    question_type = models.CharField("Type", max_length=20, choices=Type.choices, default=Type.MCQ)
    metadata = models.JSONField("Settings", default=dict, blank=True)
    label = models.CharField("Label", max_length=8, blank=True)
    marks = models.DecimalField("Marks", max_digits=4, decimal_places=2, default=1)
    order_in_set = models.PositiveSmallIntegerField("Order In Set", default=0)

    prompt_content = models.TextField("Prompt")
    model_answer = models.TextField("Model Answer", blank=True)
    explanation = models.TextField("Explanation", blank=True)

    class Meta:
        ordering = ["order_in_set", "id"]
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(block__isnull=False, question_set__isnull=True)
                    | models.Q(block__isnull=True, question_set__isnull=False)
                ),
                name="question_block_xor_set",
            )
        ]
        indexes = [
            models.Index(fields=["question_set", "order_in_set"]),
            models.Index(fields=["question_type"]),
        ]

    def __str__(self):
        return f"{self.get_question_type_display()} #{self.pk}"

    @classmethod
    def from_db(cls, db, field_names, values, *, fetch_mode=None):
        """Remembers the owner this row was loaded with, for the count signals."""
        instance = super().from_db(db, field_names, values, fetch_mode=fetch_mode)
        if "block_id" in field_names and "question_set_id" in field_names:
            instance._owner_on_load = (instance.block_id, instance.question_set_id)
        return instance

    @property
    def select_mode(self) -> str:
        return (self.metadata or {}).get("select_mode", "single")

    def clean(self):
        from apps.question.validators import validate_owner_kind, validate_single_owner  # avoids an import cycle

        validate_single_owner(self.block_id, self.question_set_id)
        validate_owner_kind(
            block=self.block if self.block_id else None,
            question_set=self.question_set if self.question_set_id else None,
        )


class QuestionOption(TimestampModel):
    """A choice on an MCQ."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    label = models.CharField("Label", max_length=8, blank=True)
    content = models.TextField("Content")
    is_correct = models.BooleanField("Correct", null=True, blank=True)
    position = models.PositiveSmallIntegerField("Position", default=0)

    class Meta:
        ordering = ["question_id", "position"]
        verbose_name = "Option"
        verbose_name_plural = "Options"
        constraints = [models.UniqueConstraint(fields=["question", "position"], name="unique_option_position")]

    def __str__(self):
        return f"{self.label or self.position}. {self.content[:40]}"
