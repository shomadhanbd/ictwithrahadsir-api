from django.db import models

from apps.core.slugs import ascii_slug, unique_slug


class ClassLevel(models.Model):
    """An education level: class 6, SSC, Dakhil, HSC, Alim, Admission."""

    name = models.CharField("Name", max_length=100, unique=True)
    slug = models.SlugField("Slug", max_length=120, unique=True, blank=True)
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
    chapter of a course; `verbose_name` keeps it distinct from `auth.Group`.
    """

    name = models.CharField("Name", max_length=100, unique=True)
    slug = models.SlugField("Slug", max_length=120, unique=True, blank=True)
    subject_count = models.PositiveIntegerField("Subject Count", default=0)
    question_count = models.PositiveIntegerField("Question Count", default=0)
    chapter_count = models.PositiveIntegerField("Chapter Count", default=0)
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Academic Group"
        verbose_name_plural = "Academic Groups"

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
    slug = models.SlugField("Slug", max_length=160, unique=True, blank=True)
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, related_name="subjects", verbose_name="Education Level"
    )
    group = models.ForeignKey(
        Group, on_delete=models.PROTECT, related_name="subjects", verbose_name="Academic Group"
    )
    question_count = models.PositiveIntegerField("Question Count", default=0)
    chapter_count = models.PositiveIntegerField("Chapter Count", default=0)
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "class_level", "group"], name="unique_subject_per_level_and_group"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.class_level} / {self.group})"

    def save(self, *args, **kwargs):
        if not self.slug:
            # From the triple, not the name: the name alone collides on every
            # level and group, giving physics-2, physics-3.
            base = f"{ascii_slug(self.name)}-{self.class_level.slug}-{self.group.slug}"
            self.slug = unique_slug(self, base)
        super().save(*args, **kwargs)


class Batch(models.Model):
    """A cohort taking one education level: "SSC-2027", "HSC-2028".

    `is_active` rather than deletion, so a finished batch keeps its students
    and results while dropping out of every picker.
    """

    name = models.CharField("Name", max_length=100)
    slug = models.SlugField("Slug", max_length=160, unique=True, blank=True)
    class_level = models.ForeignKey(
        ClassLevel, on_delete=models.PROTECT, related_name="batches", verbose_name="Education Level"
    )
    is_active = models.BooleanField("Active", default=True)
    order = models.PositiveIntegerField("Order", default=0)

    class Meta:
        ordering = ["order", "name", "id"]
        verbose_name = "Batch"
        verbose_name_plural = "Batches"
        constraints = [
            models.UniqueConstraint(fields=["name", "class_level"], name="unique_batch_per_level")
        ]

    def __str__(self):
        return f"{self.name} ({self.class_level})"

    def save(self, *args, **kwargs):
        if not self.slug:
            # The level disambiguates a bare "2027", but only when the name
            # does not already carry it, so "SSC-2027" stays `ssc-2027`.
            base = ascii_slug(self.name)
            level = self.class_level.slug
            if level not in base:
                base = f"{base}-{level}"
            self.slug = unique_slug(self, base)
        super().save(*args, **kwargs)
