"""Reusable query predicates for the course models.

Two rules were previously spelled out at several sites each:

* `active=True` plus the same three `prefetch_related` arguments, copied
  verbatim into three querysets in the views.
* "this enrolment has not expired" -- written out in `Content.is_accessible_by`,
  in a module-level helper in the views, and again in the course serializer.
  Three copies of an access rule is three chances for them to disagree about
  who is still enrolled.

Naming each once means a change lands everywhere at the same time.
"""

from django.db import models
from django.utils import timezone


class CourseQuerySet(models.QuerySet):
    #: The relations every course payload touches. Without these a page of
    #: 15 courses issues a query per course per relation.
    CATALOGUE_PREFETCH = ('categories', 'routines')

    def active(self):
        return self.filter(active=True)

    def featured(self):
        return self.filter(featured=True)

    def with_catalogue_prefetch(self):
        return self.prefetch_related(*self.CATALOGUE_PREFETCH, self._teacher_prefetch())

    @staticmethod
    def _teacher_prefetch():
        """The teacher block, in one query rather than three.

        A plain `'instructors__user__teacher'` walks the path as three
        prefetches; one `select_related` down it joins them into the query that
        fetches the assignments. Built here rather than beside
        `CATALOGUE_PREFETCH` because it needs the model, and `models` imports
        this module.
        """
        from apps.courses.models import CourseTeacher

        return models.Prefetch(
            'instructors',
            queryset=CourseTeacher.objects.select_related('user__teacher'),
        )


class EnrollmentQuerySet(models.QuerySet):
    def current(self, at=None):
        """Enrolments that have not lapsed.

        A null `valid_till` means the enrolment never expires. This is the
        single definition of "still enrolled"; anything gating access on an
        enrolment should go through it rather than re-checking the date.

        `Enrollment.is_current` is the in-memory twin of this filter, for a
        row that has already been fetched. Keep the two in step.
        """
        at = at or timezone.now()
        return self.filter(models.Q(valid_till__isnull=True) | models.Q(valid_till__gte=at))

    def for_user(self, user):
        return self.filter(user=user)


class ContentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)


class SectionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)
