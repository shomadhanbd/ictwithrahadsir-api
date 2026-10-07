"""The academic taxonomy: ClassLevel > Group > Subject > Chapter > Topic, plus Batch."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.academic.managers import ActiveQuerySet, SubjectParentQuerySet, SubjectQuerySet
from apps.core.models import OrderedModel


class ClassLevel(OrderedModel):
    """An education level: class 6, SSC, Dakhil, HSC, Alim, Admission."""

    name = models.CharField("Name", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, verbose_name=_("slug"))
    question_count = models.PositiveIntegerField("Question Count", default=0)
    is_active = models.BooleanField("Active", default=True)

    objects = SubjectParentQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Class Level"
        verbose_name_plural = "Class Levels"

    def __str__(self):
        return self.name


class Group(OrderedModel):
    """A branch of study: Science, Arts, Commerce, General."""

    name = models.CharField("Name", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, verbose_name=_("slug"))
    is_common = models.BooleanField(
        "Common to Every Group",
        default=False,
        help_text="Taken by every student on top of their own group, e.g. General (Bangla, English).",
    )
    question_count = models.PositiveIntegerField("Question Count", default=0)
    is_active = models.BooleanField("Active", default=True)

    objects = SubjectParentQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Group"
        verbose_name_plural = "Groups"

    def __str__(self):
        return self.name


class Subject(OrderedModel):
    """One subject at one level for one group; the name repeats across levels."""

    name = models.CharField("Name", max_length=100)
    slug = models.SlugField(max_length=160, unique=True, verbose_name=_("slug"))
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, related_name="subjects", verbose_name="Education Level"
    )
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="subjects")
    question_count = models.PositiveIntegerField("Question Count", default=0)
    is_active = models.BooleanField("Active", default=True)

    objects = SubjectQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        constraints = [
            models.UniqueConstraint(fields=["name", "class_level", "group"], name="unique_subject_per_level_and_group")
        ]

    def __str__(self):
        return f"{self.name} ({self.class_level} / {self.group})"


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="chapters", verbose_name="Subject")
    name = models.CharField("Name", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_("slug"))
    chapter_number = models.PositiveSmallIntegerField("Chapter Number", default=0)
    question_count = models.PositiveIntegerField("Question Count", default=0)
    practice_enabled = models.BooleanField(
        "Open for Practice",
        default=False,
        help_text=(
            "Its questions, answers included, are served free to anyone on the practice page. Off until a "
            "teacher opens it, so questions written for an upcoming exam are not given away."
        ),
    )
    is_active = models.BooleanField("Active", default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["chapter_number", "name", "id"]
        indexes = [models.Index(fields=["subject", "chapter_number"])]
        verbose_name = "Chapter"
        verbose_name_plural = "Chapters"

    def __str__(self):
        return f"{self.chapter_number}. {self.name} ({self.subject})"


class Topic(OrderedModel):
    chapter = models.ForeignKey(Chapter, on_delete=models.PROTECT, related_name="topics", verbose_name="Chapter")
    name = models.CharField("Name", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, verbose_name=_("slug"))
    question_count = models.PositiveIntegerField("Question Count", default=0)
    is_active = models.BooleanField("Active", default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Topic"
        verbose_name_plural = "Topics"

    def __str__(self):
        return f"{self.name} ({self.chapter})"


class Batch(OrderedModel):
    """A cohort taking one education level, e.g. "SSC-2027"."""

    name = models.CharField("Name", max_length=100)
    slug = models.SlugField(max_length=160, unique=True, verbose_name=_("slug"))
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, related_name="batches", verbose_name="Education Level"
    )
    is_active = models.BooleanField("Active", default=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Batch"
        verbose_name_plural = "Batches"
        constraints = [models.UniqueConstraint(fields=["name", "class_level"], name="unique_batch_per_level")]

    def __str__(self):
        return f"{self.name} ({self.class_level})"
