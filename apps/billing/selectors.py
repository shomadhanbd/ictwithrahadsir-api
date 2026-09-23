"""Reads this app owns.

`ordered_course_ids` is the one `courses` needs to fill `has_order` on the
course payload -- it must not import `Order` to find out (see
`apps.courses.selectors`), so it gets this function instead, wired in at
startup by `BillingConfig.ready`.

This module is imported from `BillingConfig.ready()`, i.e. after the app
registry is populated, so it can import models at module scope.
"""

from apps.billing.models import Order, Product


def ordered_course_ids(user, course_ids):
    """Course ids from `course_ids` that `user` has placed an order for."""
    return set(Order.objects.filter(user=user, course_id__in=course_ids).values_list('course_id', flat=True))


def owned_products(user):
    """Products `user` has paid for."""
    return (
        Product.objects.filter(orders__user=user, orders__status=Order.Status.PAID)
        .distinct()
        .prefetch_related('courses')
    )
