"""Helpers for rows a staff member orders by hand (`OrderedModel`): adding at the end and moving up or down."""

from django.db import transaction
from django.db.models import Max


def next_order(siblings) -> int:
    """The `order` for a row added after `siblings`."""
    last = siblings.aggregate(last=Max("order"))["last"]
    return 0 if last is None else last + 1


@transaction.atomic
def move(item, siblings, *, direction) -> None:
    """Swaps `item` with its neighbour among `siblings` ("up" or "down") and renumbers them 0..n."""
    rows = list(siblings.select_for_update().order_by("order", "id"))
    index = next(i for i, row in enumerate(rows) if row.pk == item.pk)
    target = index - 1 if direction == "up" else index + 1
    if 0 <= target < len(rows):
        rows[index], rows[target] = rows[target], rows[index]
    for order, row in enumerate(rows):
        if row.order != order:
            row.order = order
            row.save(update_fields=["order", "updated_at"])
