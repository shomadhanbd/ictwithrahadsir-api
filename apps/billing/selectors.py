"""Read helpers this app exposes to others.

`courses` needs to know which courses a user has ordered, to fill
`has_order` on the course payload. It must not import `Order` to find out
-- see `apps.courses.selectors`. This is the function it gets instead,
wired in at startup by `BillingConfig.ready`.
"""

from apps.billing.models import Order


def ordered_course_ids(user, course_ids):
    """Course ids from `course_ids` that `user` has placed an order for."""
    return set(
        Order.objects.filter(user=user, course_id__in=course_ids).values_list(
            'course_id', flat=True
        )
    )
