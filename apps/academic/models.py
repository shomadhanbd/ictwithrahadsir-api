"""The academic taxonomy: ClassLevel > Group > Subject > Chapter > Topic, plus
Batch as a cohort of one level.

Each level `PROTECT`s the one above it, so nothing in use can be deleted;
`is_active` is how you retire a row instead.

`question_count`, `ClassLevel.subject_count` and `Subject.chapter_count` are
recounted on demand by `apps.question.counts` (the Question Bank's "Refresh
questions" button); the other `*_count` fields are typed in.

Slugs are English. A blank one is built from the name (see
`apps.core.slugs`), so a Bangla-named row should be given a slug explicitly.
"""

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.slugs import unique_slug


class ClassLevel(models.Model):
    """An education level: class 6, SSC, Dakhil, HSC, Alim, Admission."""

    name = models.CharField("Name", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, verbose_name=_("slug"))
    group_count = models.PositiveIntegerField("Group Count", default=0)
    subject_count = models.PositiveIntegerField("Subject Count", default=0)
    question_count = models.PositiveIntegerField("Question Count", default=0)
    chapter_count = models.PositiveIntegerField("Chapter Count", default=0)
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Class Level"
        verbose_name_plural = "Class Levels"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Group(models.Model):
    """A branch of study: Science, Arts, Commerce, General.

    Named `Group` rather than `Section` because `courses.Section` is already a
    chapter of a course. The Django admin lists it under Academic, which is
    what separates it from `auth.Group`.
    """

    name = models.CharField("Name", max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True, verbose_name=_("slug"))
    subject_count = models.PositiveIntegerField("Subject Count", default=0)
    question_count = models.PositiveIntegerField("Question Count", default=0)
    chapter_count = models.PositiveIntegerField("Chapter Count", default=0)
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.name)
        super().save(*args, **kwargs)


class Subject(models.Model):
    """One subject, as taught at one education level to one group.

    "Physics" is not a single row: SSC Science Physics, HSC Science Physics and
    Alim Science Physics each carry their own chapters and question count. The
    name repeats, and the triple is what has to be unique.
    """

    name = models.CharField("Name", max_length=100)
    slug = models.SlugField(max_length=160, unique=True, blank=True, verbose_name=_("slug"))
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, related_name="subjects", verbose_name="Education Level"
    )
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="subjects")
    question_count = models.PositiveIntegerField("Question Count", default=0)
    chapter_count = models.PositiveIntegerField("Chapter Count", default=0)
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        constraints = [
            models.UniqueConstraint(fields=["name", "class_level", "group"], name="unique_subject_per_level_and_group")
        ]

    def __str__(self):
        return f"{self.name} ({self.class_level} / {self.group})"

    def save(self, *args, **kwargs):
        if not self.slug:
            # From the triple, not the name: the name alone collides on every
            # level and group, giving physics-2, physics-3.
            base = f"{slugify(self.name)}-{self.class_level.slug}-{self.group.slug}"
            self.slug = unique_slug(self, base)
        super().save(*args, **kwargs)


class Chapter(models.Model):
    """A chapter within a subject.

    Uniqueness is carried by the slug alone: two chapters of one subject may
    share a `chapter_number` or a `name`, and the second is suffixed rather
    than rejected.
    """

    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="chapters", verbose_name="Subject")
    name = models.CharField("Name", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name=_("slug"))
    chapter_number = models.PositiveSmallIntegerField("Chapter Number", default=0)
    question_count = models.PositiveIntegerField("Question Count", default=0)
    is_locked = models.BooleanField(
        "Locked",
        default=False,
        help_text=(
            "Locked chapters appear in lists with is_locked=True so clients can render "
            "a lock badge. Does not gate question access by itself."
        ),
    )
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        ordering = ["chapter_number", "name", "id"]
        indexes = [models.Index(fields=["subject", "chapter_number"])]
        verbose_name = "Chapter"
        verbose_name_plural = "Chapters"

    def __str__(self):
        return f"{self.chapter_number}. {self.name} ({self.subject})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, f"{slugify(self.name)}-{self.subject.slug}")
        super().save(*args, **kwargs)


class Topic(models.Model):
    """A topic within a chapter -- the most granular curriculum unit."""

    chapter = models.ForeignKey(Chapter, on_delete=models.PROTECT, related_name="topics", verbose_name="Chapter")
    name = models.CharField("Name", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name=_("slug"))
    question_count = models.PositiveIntegerField("Question Count", default=0)
    is_active = models.BooleanField("Active", default=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Topic"
        verbose_name_plural = "Topics"

    def __str__(self):
        return f"{self.name} ({self.chapter})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, f"{slugify(self.name)}-{self.chapter.slug}")
        super().save(*args, **kwargs)


class Batch(models.Model):
    """A cohort taking one education level: "SSC-2027", "HSC-2028".

    `is_active` rather than deletion, so a finished batch keeps its students
    and results while dropping out of every picker.
    """

    name = models.CharField("Name", max_length=100)
    slug = models.SlugField(max_length=160, unique=True, blank=True, verbose_name=_("slug"))
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, related_name="batches", verbose_name="Education Level"
    )
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Batch"
        verbose_name_plural = "Batches"
        constraints = [models.UniqueConstraint(fields=["name", "class_level"], name="unique_batch_per_level")]

    def __str__(self):
        return f"{self.name} ({self.class_level})"

    def save(self, *args, **kwargs):
        if not self.slug:
            # The level disambiguates a bare "2027", but only when the name
            # does not already carry it, so "SSC-2027" stays `ssc-2027`.
            base = slugify(self.name)
            level = self.class_level.slug
            if level not in base:
                base = f"{base}-{level}"
            self.slug = unique_slug(self, base)
        super().save(*args, **kwargs)
