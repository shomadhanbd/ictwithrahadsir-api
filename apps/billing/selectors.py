from collections import defaultdict

from django.conf import settings
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils import timezone

from apps.billing.models import Payment, Product

CHECKOUT_REUSE_MINUTES = 10
# How long a checkout may wait on its gateway page before another may be opened.
CHECKOUT_OPENING_SECONDS = 35


def running_purchase(user, product, *, exclude=None):
    """The buyer's paid purchase of `product` whose access has not ended, longest first; lifetime wins.

    A refund-due duplicate gave no access, so it never counts. `user` and `product` may be pks.
    """
    payments = Payment.objects.filter(user=user, product=product, status=Payment.Status.VALID, refund_due=False)
    payments = payments.filter(Q(access_until__isnull=True) | Q(access_until__gt=timezone.now()))
    if exclude is not None:
        payments = payments.exclude(pk=exclude.pk)
    return payments.order_by(F("access_until").desc(nulls_first=True)).first()


def renewal_window():
    """How long before a running purchase ends it may be renewed; the expiry reminder goes out as it opens."""
    return timezone.timedelta(days=settings.EXPIRY_REMINDER_DAYS)


def access_until(product, *, user=None):
    """When a purchase made now stops giving access; None is lifetime.

    A renewal of `user`'s running purchase of a fixed-days package adds its days to that purchase's end.
    """
    if product.access_ends_at:
        return product.access_ends_at
    if product.access_days:
        start = timezone.now()
        running = running_purchase(user, product) if user is not None else None
        if running is not None and running.access_until is not None:
            start = max(start, running.access_until)
        return start + timezone.timedelta(days=product.access_days)
    return None


def open_checkout(user, product, amount):
    """A checkout for the same package started moments ago and not yet settled, e.g. a double click.

    Either it has its gateway page, to hand back, or it is still waiting on one. One started before the
    package was last edited is not reused: its price or access may be stale.
    """
    now = timezone.now()
    since = max(now - timezone.timedelta(minutes=CHECKOUT_REUSE_MINUTES), product.updated_at)
    opening = now - timezone.timedelta(seconds=CHECKOUT_OPENING_SECONDS)
    return (
        Payment.objects.filter(
            user=user, product=product, amount=amount, status=Payment.Status.INITIATED, created_at__gte=since
        )
        .filter(~Q(gateway_page_url="") | Q(created_at__gte=opening))
        .order_by("-created_at")
        .first()
    )


def ordered_course_ids(user, course_ids):
    """The courses among `course_ids` that `user` has bought a product for."""
    return set(
        Payment.objects.filter(user=user, status=Payment.Status.VALID, product__courses__in=course_ids).values_list(
            'product__courses', flat=True
        )
    )


def sold_course_ids(course_ids) -> set:
    """The courses among `course_ids` that anyone has paid for."""
    return set(
        Payment.objects.filter(status=Payment.Status.VALID, product__courses__in=course_ids).values_list(
            'product__courses', flat=True
        )
    )


def package_summary(product, course_count) -> dict:
    """A product as a course payload shows it: what it costs and for how long."""
    return {
        'id': product.id,
        'product_id': product.product_id,
        'title': product.title,
        'price': product.current_price,
        'base_price': product.base_price if product.discount_active else product.current_price,
        'discount_ends_at': product.discount_ends_at if product.discount_active else None,
        'access_days': product.access_days,
        'access_ends_on': product.access_ends_on,
        'course_count': course_count,
    }


def course_packages(course_ids, user=None) -> dict[int, list[dict]]:
    """The packages on sale to `user` for each of `course_ids`, cheapest first."""
    link = Product.courses.through
    course_count = (
        link.objects.filter(product_id=OuterRef('product_id'))
        .order_by()
        .values('product_id')
        .annotate(total=Count('id'))
        .values('total')
    )
    rows = (
        link.objects.filter(course_id__in=course_ids, product__in=Product.objects.on_sale().visible_to(user))
        .select_related('product')
        .annotate(course_count=Subquery(course_count))
    )
    by_course = defaultdict(list)
    for row in rows:
        by_course[row.course_id].append(package_summary(row.product, row.course_count))
    for packages in by_course.values():
        packages.sort(key=lambda package: (package['price'], package['id']))
    return dict(by_course)
