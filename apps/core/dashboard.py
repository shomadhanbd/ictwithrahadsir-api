from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncMonth
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import IsAdminRole


def _month_bounds(now):
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _year_bounds(now):
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_dashboard(request):
    from apps.accounts.models import User
    from apps.courses.models import Course
    from apps.shop.models import Order

    now = timezone.now()
    month_start = _month_bounds(now)
    year_start = _year_bounds(now)

    paid_orders = Order.objects.filter(status=Order.Status.PAID)

    def income_since(since):
        return paid_orders.filter(created_at__gte=since).aggregate(total=Sum("amount"))["total"] or 0

    def orders_since(status, since):
        return Order.objects.filter(status=status, created_at__gte=since).count()

    students_since = lambda since: User.objects.filter(  # noqa: E731
        role=User.Role.STUDENT, date_joined__gte=since
    ).count()

    return Response(
        {
            "income": {
                "thisMonth": income_since(month_start),
                "thisYear": income_since(year_start),
                "lifeTime": paid_orders.aggregate(total=Sum("amount"))["total"] or 0,
            },
            "orders": {
                "completed": {
                    "thisMonth": orders_since(Order.Status.PAID, month_start),
                    "thisYear": orders_since(Order.Status.PAID, year_start),
                },
                "incomplete": {
                    "thisMonth": orders_since(Order.Status.PENDING, month_start),
                    "thisYear": orders_since(Order.Status.PENDING, year_start),
                },
            },
            "totalCounts": {
                "courses": Course.objects.filter(active=True).count(),
                "students": User.objects.filter(role=User.Role.STUDENT).count(),
            },
            "studentsRegistered": {
                "thisMonth": students_since(month_start),
                "thisYear": students_since(year_start),
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_dashboard_sales_overview(request):
    from apps.shop.models import Order

    now = timezone.now()
    start = now.replace(day=1) - timezone.timedelta(days=365)
    rows = (
        Order.objects.filter(status=Order.Status.PAID, created_at__gte=start)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    months = [row["month"].strftime("%Y-%m") for row in rows]
    course_sales = [row["count"] for row in rows]
    return Response({"months": months, "courseSales": course_sales})


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_dashboard_payment_chart(request):
    from apps.shop.models import Order

    now = timezone.now()
    start = now - timezone.timedelta(days=30)
    rows = (
        Order.objects.filter(status=Order.Status.PAID, created_at__gte=start)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(total=Sum("amount"))
        .order_by("day")
    )
    all_days = [row["day"].strftime("%Y-%m-%d") for row in rows]
    income = [float(row["total"] or 0) for row in rows]
    return Response({"allDays": all_days, "income": income})


@api_view(["GET"])
@permission_classes([IsAdminRole])
def sms_balance(request):
    """Real SMS balance requires a live gateway account; stubbed until one
    is configured (see settings.SMS_BACKEND)."""
    return Response({"balance": 0, "currency": "BDT"})
