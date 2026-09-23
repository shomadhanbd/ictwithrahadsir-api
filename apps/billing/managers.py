"""Reusable query predicates for the billing models.

Naming `paid()` / `since()` once means the `status`/`created_at` index (see
`Order.Meta`) has one place to be kept in step with the queries that use it.
"""

from django.db import models


class OrderQuerySet(models.QuerySet):
    def paid(self):
        """Orders that have been confirmed as paid."""
        return self.filter(status=self.model.Status.PAID)

    def pending(self):
        return self.filter(status=self.model.Status.PENDING)

    def with_status(self, status):
        return self.filter(status=status)

    def since(self, when):
        """Orders created at or after `when`."""
        return self.filter(created_at__gte=when)

    def for_user(self, user):
        return self.filter(user=user)


class PaymentQuerySet(models.QuerySet):
    def with_payer(self):
        """Preload the order and its user.

        The admin payment list renders the payer's name and phone for every
        row, which is two extra queries per payment without this.
        """
        return self.select_related('order', 'order__user')

    def with_status(self, status):
        return self.filter(status=status)
