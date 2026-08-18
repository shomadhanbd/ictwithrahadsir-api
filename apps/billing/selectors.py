"""Reads this app owns.

Two kinds live here. `ordered_course_ids` is the one `courses` needs to fill
`has_order` on the course payload -- it must not import `Order` to find out
(see `apps.courses.selectors`), so it gets this function instead, wired in at
startup by `BillingConfig.ready`. The rest are the admin dashboard's
aggregates, which are pure reads and so do not belong in a view.

This module is imported from `BillingConfig.ready()`, i.e. after the app
registry is populated, so it can import models at module scope.
"""

from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone

from apps.billing.models import Order
from apps.courses.models import Course
from apps.identity.models import User


def ordered_course_ids(user, course_ids):
    """Course ids from `course_ids` that `user` has placed an order for."""
    return set(
        Order.objects.filter(user=user, course_id__in=course_ids).values_list(
            'course_id', flat=True
        )
    )


# ---------------------------------------------------------------------------
# Admin dashboard
#
# These live here rather than in the views because they are reads that say
# nothing about HTTP: each returns plain numbers or rows, so the shape of the
# dashboard payload is decided by a serializer and the arithmetic is testable
# on its own.
#
# Counting courses and students crosses into `courses` and `identity`, which
# adds no new dependency edge: `Order` already holds foreign keys to both.
# ---------------------------------------------------------------------------


def _month_start(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _year_start(now):
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


def dashboard_totals(now=None):
    """The headline counters on the admin panel's landing page."""
    now = now or timezone.now()
    month_start = _month_start(now)
    year_start = _year_start(now)

    paid_orders = Order.objects.paid()

    def income_since(since):
        return paid_orders.since(since).aggregate(total=Sum('amount'))['total'] or 0

    def orders_since(status, since):
        return Order.objects.with_status(status).since(since).count()

    def students_since(since):
        return User.objects.students().joined_since(since).count()

    return {
        'income': {
            'thisMonth': income_since(month_start),
            'thisYear': income_since(year_start),
            'lifeTime': paid_orders.aggregate(total=Sum('amount'))['total'] or 0,
        },
        'orders': {
            'completed': {
                'thisMonth': orders_since(Order.Status.PAID, month_start),
                'thisYear': orders_since(Order.Status.PAID, year_start),
            },
            'incomplete': {
                'thisMonth': orders_since(Order.Status.PENDING, month_start),
                'thisYear': orders_since(Order.Status.PENDING, year_start),
            },
        },
        'totalCounts': {
            'courses': Course.objects.filter(active=True).count(),
            'students': User.objects.students().count(),
        },
        'studentsRegistered': {
            'thisMonth': students_since(month_start),
            'thisYear': students_since(year_start),
        },
    }


def monthly_sales(since=None):
    """Paid-order counts per month, oldest first."""
    since = since or (timezone.now().replace(day=1) - timezone.timedelta(days=365))
    rows = (
        Order.objects.paid()
        .since(since)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    return {
        'months': [row['month'].strftime('%Y-%m') for row in rows],
        'courseSales': [row['count'] for row in rows],
    }


def daily_income(since=None):
    """Paid-order income per day, oldest first."""
    since = since or (timezone.now() - timezone.timedelta(days=30))
    rows = (
        Order.objects.paid()
        .since(since)
        .annotate(day=TruncDay('created_at'))
        .values('day')
        .annotate(total=Sum('amount'))
        .order_by('day')
    )
    return {
        'allDays': [row['day'].strftime('%Y-%m-%d') for row in rows],
        'income': [float(row['total'] or 0) for row in rows],
    }
