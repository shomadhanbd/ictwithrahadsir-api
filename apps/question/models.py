"""The question bank: blocks, stimulus sets, questions and their options.

A chapter's feed mixes single questions with stimulus groups (উদ্দীপক) that carry
several questions between them. `QuestionBlock` exists so both paginate as equal
items: it holds the scoping and the ordering once, and questions hold only
content. Without it, a page of a chapter is a `UNION` of two tables ordered and
offset across both.

Content fields hold HTML with LaTeX (`$…$`) and are rendered by the client. They
are stored as written -- nothing sanitizes them yet. That was tolerable while
only admins authored; since `apps.exam` opened the bank to every teacher it is
a stored-XSS surface with a much wider write population, and `bleach` is now
overdue rather than merely pending.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimestampModel
from apps.core.slugs import unique_slug


class QuestionSource(TimestampModel):
    """One exam a question appeared in: ঢাকা বোর্ড ২০১৯, ঢাবি ক-ইউনিট ২০২১.

    A row is shared by every block that appeared in that exam. Three flat
    `source_*` columns on the block could only record one appearance, and a
    question is routinely asked again -- another board the same year, another
    college test, another admission unit.

    Shared rather than owned by the block so that "ঢাকা বোর্ড ২০১৯" is one thing
    that can be listed, counted and offered as a paper to practise, instead of a
    string retyped per question that drifts into four spellings.
    """

    class Kind(models.TextChoices):
        BOARD = "board", "Board"
        COLLEGE = "college", "College"
        UNIVERSITY = "university", "University"
        SCHOOL = "school", "School"
        OTHER = "other", "Other"

    kind = models.CharField("Kind", max_length=20, choices=Kind.choices, default=Kind.BOARD)
    name = models.CharField("Name", max_length=150)
    #: Nullable: a question may be known to come from a board paper without the
    #: year having been recorded.
    year = models.PositiveSmallIntegerField("Year", null=True, blank=True)
    #: Admission units -- ক, খ, গ. Empty for board and school papers.
    unit = models.CharField("Unit", max_length=20, blank=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name=_("slug"))
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        ordering = [models.F("year").desc(nulls_last=True), "kind", "name"]
        verbose_name = "Question Source"
        verbose_name_plural = "Question Sources"
        constraints = [
            models.UniqueConstraint(fields=["kind", "name", "year", "unit"], name="unique_question_source"),
            #: NULL never equals NULL, so the constraint above lets undated rows
            #: duplicate freely. Django 5.0 has no `nulls_distinct`, so the
            #: undated case needs a constraint of its own.
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

    def save(self, *args, **kwargs):
        if not self.slug:
            # Built from the label, so two years of the same board do not
            # collide.
            self.slug = unique_slug(self, self.label)
        super().save(*args, **kwargs)


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
    #: Nullable: some content belongs to a subject without a chapter.
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
    #: 1 for a standalone block, N for a group. Maintained on write by
    #: `services.sync_question_count`, not by a backfill script.
    question_count = models.PositiveSmallIntegerField("Question Count", default=0)
    slug = models.SlugField("Slug", max_length=32, unique=True, blank=True)

    #: Many, not one: the same question turns up in several boards and years.
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

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.slug:
            # The slug needs the pk, so it costs a second write. Bulk imports
            # skip `save()` entirely and must set slugs themselves.
            self.slug = f"b-{self.pk}"
            super().save(update_fields=["slug"])


class QuestionSet(TimestampModel):
    """The shared stimulus of a group block.

    Carries no scoping of its own -- subject, chapter and topics all come from
    the block.
    """

    class StimulusType(models.TextChoices):
        TEXT = "text", "Text"
        IMAGE = "image", "Image"
        TABLE = "table", "Table"
        DIAGRAM = "diagram", "Diagram"
        CODE = "code", "Code"
        COMPOSITE = "composite", "Composite"

    block = models.OneToOneField(QuestionBlock, on_delete=models.CASCADE, related_name="question_set")
    #: A rendering hint for the client, nothing more.
    stimulus_type = models.CharField(max_length=20, choices=StimulusType.choices, blank=True)
    stimulus_content = models.TextField("Stimulus")
    slug = models.SlugField("Slug", max_length=32, unique=True, blank=True)

    class Meta:
        verbose_name = "Question Set"
        verbose_name_plural = "Question Sets"

    def __str__(self):
        return f"Stimulus #{self.pk}"

    def clean(self):
        # Imported here, not at module scope: `services` imports this module.
        from apps.question import services

        services.validate_set_block(self.block if self.block_id else None)

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.slug:
            self.slug = f"qs-{self.pk}"
            super().save(update_fields=["slug"])


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
    #: Whatever this *type* needs and no other does -- MCQ's `select_mode`
    #: lives here. It was a column, which is fine for one type and a table of
    #: mostly-NULLs at eight. `apps.question.types` declares the shape each
    #: type allows, and `clean_metadata` enforces it.
    #:
    #: A payload, never a filter: `JSONField__contains` is unsupported on
    #: SQLite, so anything that has to be queried stays a column.
    metadata = models.JSONField("Settings", default=dict, blank=True)
    label = models.CharField("Label", max_length=8, blank=True)
    marks = models.DecimalField("Marks", max_digits=4, decimal_places=2, default=1)
    order_in_set = models.PositiveSmallIntegerField("Order In Set", default=0)

    prompt_content = models.TextField("Prompt")
    model_answer = models.TextField("Model Answer", blank=True)
    explanation = models.TextField("Explanation", blank=True)
    slug = models.SlugField("Slug", max_length=32, unique=True, blank=True)

    class Meta:
        #: Without this a grouped block returns its questions in whatever order
        #: the database felt like, so ক/খ/গ/ঘ arrive shuffled.
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
        """Remember which owner this row was loaded with.

        A question that is moved to another block leaves the old block's
        `question_count` one too high, and `post_save` only ever sees the new
        owner. Snapshotting on load is what lets the signal fix both.

        `fetch_mode` is passed straight through: Django 6.1 hands it to every
        `from_db`, and an override that swallows it is an error in 7.0.
        """
        instance = super().from_db(db, field_names, values, fetch_mode=fetch_mode)
        if "block_id" in field_names and "question_set_id" in field_names:
            instance._owner_on_load = (instance.block_id, instance.question_set_id)
        return instance

    def clean(self):
        from apps.question import services

        if bool(self.block_id) == bool(self.question_set_id):
            raise ValidationError("A question belongs to either a block or a set, not both.")

        services.validate_owner_kind(
            block=self.block if self.block_id else None,
            question_set=self.question_set if self.question_set_id else None,
        )

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.slug:
            self.slug = f"q-{self.pk}"
            super().save(update_fields=["slug"])


class QuestionOption(TimestampModel):
    """A choice on an MCQ."""

    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    label = models.CharField("Label", max_length=8, blank=True)
    content = models.TextField("Content")
    #: Null means "not applicable" -- kept nullable so option-bearing types that
    #: have no notion of correctness can reuse this table.
    is_correct = models.BooleanField("Correct", null=True, blank=True)
    position = models.PositiveSmallIntegerField("Position", default=0)

    class Meta:
        ordering = ["question_id", "position"]
        verbose_name = "Option"
        verbose_name_plural = "Options"
        constraints = [models.UniqueConstraint(fields=["question", "position"], name="unique_option_position")]

    def __str__(self):
        return f"{self.label or self.position}. {self.content[:40]}"
