from django.db import models
from django.db.models import Count, DurationField, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.querysets import with_stable_order


class ExamQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=self.model.Status.PUBLISHED)

    def course_exams(self):
        return self.filter(scope=self.model.Scope.COURSE)

    def results_released(self, now=None):
        """At the result time; with none set, once the exam closes; with neither, at once."""
        now = now or timezone.now()
        return self.filter(
            Q(status__in=[self.model.Status.PUBLISHED, self.model.Status.ARCHIVED])
            & (
                Q(result_publish_time__lte=now)
                | Q(result_publish_time__isnull=True, end_time__lte=now)
                | Q(result_publish_time__isnull=True, end_time__isnull=True)
            )
        )

    def with_admin_totals(self):
        attempts = (
            self.model.attempts.rel.related_model.objects.filter(exam=OuterRef("pk"))
            .order_by()
            .values("exam")
            .annotate(n=Count("id"))
            .values("n")
        )
        totals = self.annotate(
            section_count=Count("sections", distinct=True),
            selected_question_count=Sum("sections__question_count"),
            computed_marks=Sum("sections__computed_marks"),
            attempt_count=Coalesce(Subquery(attempts, output_field=IntegerField()), 0),
        )
        return with_stable_order(totals)


class ExamAttemptQuerySet(models.QuerySet):
    def in_progress(self):
        return self.filter(status=self.model.Status.IN_PROGRESS)

    def submitted(self):
        return self.filter(status=self.model.Status.SUBMITTED)

    def official(self):
        return self.filter(is_official=True)

    def expired(self, now=None):
        return self.in_progress().filter(deadline__lte=now or timezone.now())

    def search(self, term):
        term = (term or "").strip()
        if not term:
            return self
        return self.filter(Q(user__name__icontains=term) | Q(user__phone__contains=term))

    def results_table(self):
        """Official attempts in rank order (higher score, then quicker), then practice ones.

        The order `selectors.official_ranks` ranks in, so a page of the table holds consecutive ranks.
        """
        took = ExpressionWrapper(F("submitted_at") - F("started_at"), output_field=DurationField())
        return (
            self.select_related("user")
            .annotate(took=took)
            .order_by("-is_official", F("score").desc(nulls_last=True), F("took").asc(nulls_last=True), "pk")
        )
