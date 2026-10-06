"""Queryset helpers shared by the apps' managers."""


def with_stable_order(queryset):
    """An aggregating queryset drops `Meta.ordering`, so pages could repeat or skip rows; this puts it back.

    An order the caller already chose is kept; the pk breaks ties either way.
    """
    order = list(queryset.query.order_by) or list(queryset.model._meta.ordering)
    return queryset.order_by(*order, "pk")
