from django.db import models
from django.db.models import Count
from django.utils import timezone

from apps.core.querysets import with_stable_order


def current_q(at=None):
    """Access that has not expired; a null `valid_till` never does."""
    return models.Q(valid_till__isnull=True) | models.Q(valid_till__gte=at or timezone.now())


class CourseQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=self.model.Status.PUBLISHED)

    def available(self):
        """Courses enrolled students can still use: published or archived."""
        return self.filter(status__in=(self.model.Status.PUBLISHED, self.model.Status.ARCHIVED))

    def featured(self):
        return self.filter(is_featured=True)

    def visible_to(self, user):
        """Students with a class level see open courses and those for their level and group."""
        if user is None or not user.is_authenticated:
            return self

        profile = getattr(user, "student", None)
        if profile is None or profile.class_level_id is None:
            return self

        for_level = models.Q(class_level_id=profile.class_level_id) & (
            models.Q(group__isnull=True) | models.Q(group_id=profile.group_id)
        )
        return self.filter(models.Q(class_level__isnull=True) | for_level)

    def with_catalogue_prefetch(self):
        teachers = self.model._meta.get_field("instructors").related_model.objects.select_related("user__teacher")
        return self.select_related("class_level", "group", "batch").prefetch_related(
            models.Prefetch("instructors", queryset=teachers)
        )

    def with_enrolled_count(self):
        return with_stable_order(self.annotate(enrolled_count=Count("enrollments", distinct=True)))


class EnrollmentQuerySet(models.QuerySet):
    def current(self, at=None):
        return self.filter(current_q(at))


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active=True)
