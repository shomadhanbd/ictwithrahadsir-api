from django.db.models import Count, Q

from apps.billing.models import Payment
from apps.core.querysets import with_stable_order
from apps.courses.models import Enrollment
from apps.identity.roles import is_staff_member
from apps.materials.models import BookOrder, MaterialCategory, MaterialItem, MaterialTopic


def _with_item_counts(topics):
    counts = {f"{kind}_count": Count("items", filter=Q(items__kind=kind)) for kind in MaterialItem.Kind.values}
    return topics.annotate(**counts)


def library_topics(*, class_level=None):
    """Published topics in active categories with their items; a class filter keeps topics for every class."""
    topics = MaterialTopic.objects.filter(is_published=True, category__is_active=True)
    if class_level:
        topics = topics.filter(Q(class_level__isnull=True) | Q(class_level__slug=class_level))
    return topics.select_related("category", "class_level", "group").prefetch_related("courses", "items")


def opens_for(user):
    """Returns `opens(topic) -> bool` for `user`, reading their enrolments once."""
    if is_staff_member(user):
        return lambda topic: True
    enrolled = set()
    if user is not None and user.is_authenticated:
        enrolled = set(Enrollment.objects.current().filter(user=user).values_list("course_id", flat=True))

    def opens(topic) -> bool:
        if topic.access == MaterialTopic.Access.FREE:
            return True
        return any(course.pk in enrolled for course in topic.courses.all())

    return opens


def book_for_sale(item_id):
    return (
        MaterialItem.objects.filter(
            pk=item_id,
            kind=MaterialItem.Kind.BOOK,
            price__isnull=False,
            topic__is_published=True,
            topic__category__is_active=True,
        )
        .select_related("topic")
        .prefetch_related("topic__courses")
        .first()
    )


def admin_categories():
    return MaterialCategory.objects.annotate(topic_count=Count("topics"))


def admin_topics():
    # The item counts add a GROUP BY, which drops Meta.ordering; paging needs a fixed order.
    return with_stable_order(
        _with_item_counts(MaterialTopic.objects.select_related("category").prefetch_related("courses"))
    )


def paid_book_orders():
    return BookOrder.objects.filter(payment__status=Payment.Status.VALID).select_related("payment", "payment__user")
