from django.db import models
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.courses.models import Course


class ProductQuerySet(models.QuerySet):
    def on_sale(self):
        """Active, ending after today, and every course in it published and open for enrolment.

        A package ending today is not sold: full price for a few hours of access.
        """
        return (
            self.filter(
                Q(access_ends_on__isnull=True) | Q(access_ends_on__gt=timezone.localdate()),
                is_active=True,
                courses__isnull=False,
            )
            .exclude(courses__enrollment_deadline__lt=timezone.now())
            .exclude(courses__in=Course.objects.exclude(status=Course.Status.PUBLISHED))
            .distinct()
        )

    def visible_to(self, user):
        """Packages whose every course the viewer would see in the course list, or is enrolled on (to renew)."""
        hidden = Course.objects.exclude(pk__in=Course.objects.visible_to(user).values("pk"))
        if user is not None and user.is_authenticated:
            hidden = hidden.exclude(enrollments__user=user)
        return self.exclude(courses__in=hidden)


class PaymentQuerySet(models.QuerySet):
    def paid(self):
        return self.filter(status=self.model.Status.VALID)

    def awaiting(self):
        return self.filter(status=self.model.Status.INITIATED)

    def with_paid_on(self):
        """`paid_on`: the gateway's transaction time, else when the row was made (cash sales)."""
        return self.annotate(paid_on=Coalesce("transaction_date", "created_at"))
