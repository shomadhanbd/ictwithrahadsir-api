from django.db import models
from django.db.models import Count

from apps.core.querysets import with_stable_order


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class SubjectParentQuerySet(ActiveQuerySet):
    """For class levels and groups, which both hold subjects."""

    def with_counts(self):
        counted = self.annotate(
            subject_count=Count("subjects", distinct=True),
            chapter_count=Count("subjects__chapters", distinct=True),
        )
        return with_stable_order(counted)


class SubjectQuerySet(ActiveQuerySet):
    def with_counts(self):
        return with_stable_order(self.annotate(chapter_count=Count("chapters", distinct=True)))
