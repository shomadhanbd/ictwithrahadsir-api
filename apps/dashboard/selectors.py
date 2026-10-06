"""Read-only figures for the admin dashboard; this app owns no models."""

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from apps.billing.models import Payment
from apps.courses.models import Course, Enrollment
from apps.identity.models import User
from apps.identity.roles import is_full_admin

SALES_MONTHS = 12
INCOME_DAYS = 30


def _period_starts(now):
    local = timezone.localtime(now)
    month = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month, month.replace(month=1)


def _this_month_and_year(queryset, field, now, *, total=None):
    month, year = _period_starts(now)
    measure = Coalesce(Sum(total), 0) if total else Count("pk")
    return {
        "thisMonth": queryset.filter(**{f"{field}__gte": month}).aggregate(n=measure)["n"],
        "thisYear": queryset.filter(**{f"{field}__gte": year}).aggregate(n=measure)["n"],
    }


def dashboard_summary(viewer, now=None) -> dict:
    """Everything for an admin; a teacher gets only their own courses and students, never money."""
    now = now or timezone.now()
    if not is_full_admin(viewer):
        return teacher_summary(viewer, now)
    paid = Payment.objects.paid().with_paid_on()
    students = User.objects.students()
    return {
        "income": {
            "lifeTime": paid.aggregate(n=Coalesce(Sum("amount"), 0))["n"],
            **_this_month_and_year(paid, "paid_on", now, total="amount"),
        },
        "orders": {
            "completed": _this_month_and_year(paid, "paid_on", now),
            "incomplete": _this_month_and_year(Payment.objects.awaiting(), "created_at", now),
        },
        "totalCounts": {"courses": Course.objects.count(), "students": students.count()},
        "studentsRegistered": {
            "thisMonth": students.joined_since(_period_starts(now)[0]).count(),
            "thisYear": students.joined_since(_period_starts(now)[1]).count(),
        },
    }


def teacher_summary(teacher, now) -> dict:
    month, year = _period_starts(now)
    taught = Course.objects.filter(instructors__user=teacher)
    enrollments = Enrollment.objects.filter(course__in=taught, user__in=User.objects.students())

    def students(queryset):
        return queryset.values("user_id").distinct().count()

    return {
        "income": None,
        "orders": None,
        "totalCounts": {"courses": taught.count(), "students": students(enrollments)},
        "studentsRegistered": {
            "thisMonth": students(enrollments.filter(created_at__gte=month)),
            "thisYear": students(enrollments.filter(created_at__gte=year)),
        },
    }


def _month_keys(now, count):
    local = timezone.localtime(now)
    year, month = local.year, local.month
    keys = []
    for _ in range(count):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return keys[::-1]


def sales_overview(now=None) -> dict:
    """Completed orders per month, oldest first, for the last `SALES_MONTHS` months."""
    now = now or timezone.now()
    months = _month_keys(now, SALES_MONTHS)
    first = timezone.make_aware(timezone.datetime.strptime(months[0], "%Y-%m"))
    rows = (
        Payment.objects.paid()
        .with_paid_on()
        .filter(paid_on__gte=first)
        .annotate(month=TruncMonth("paid_on"))
        .values("month")
        .annotate(n=Count("pk"))
    )
    counts = {timezone.localtime(row["month"]).strftime("%Y-%m"): row["n"] for row in rows}
    return {"months": months, "courseSales": [counts.get(month, 0) for month in months]}


def payment_chart(now=None) -> dict:
    """Income per day, oldest first, for the last `INCOME_DAYS` days including today."""
    today = timezone.localdate(now or timezone.now())
    days = [today - timezone.timedelta(days=offset) for offset in range(INCOME_DAYS - 1, -1, -1)]
    first = timezone.make_aware(timezone.datetime.combine(days[0], timezone.datetime.min.time()))
    rows = (
        Payment.objects.paid()
        .with_paid_on()
        .filter(paid_on__gte=first)
        .annotate(day=TruncDate("paid_on"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    totals = {row["day"]: row["total"] for row in rows}
    return {"allDays": [day.isoformat() for day in days], "income": [totals.get(day, 0) for day in days]}
