from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import Payment
from apps.billing.selectors import CHECKOUT_OPENING_SECONDS, CHECKOUT_REUSE_MINUTES
from apps.billing.services import MIN_AMOUNT, open_gateway_session, throttle_initiate
from apps.billing.services.settlement import lock_buyer
from apps.core.ordering import move, next_order
from apps.materials.models import BookOrder, DeliveryRate, MaterialItem
from apps.materials.selectors import book_for_sale, opens_for


def move_item(item, *, direction) -> None:
    move(item, MaterialItem.objects.filter(topic_id=item.topic_id), direction=direction)


def next_item_order(topic) -> int:
    return next_order(topic.items.all())


def _open_order(user, item, amount, delivery):
    """The same unpaid order started moments ago, e.g. by a double click."""
    now = timezone.now()
    since = max(now - timezone.timedelta(minutes=CHECKOUT_REUSE_MINUTES), item.updated_at)
    opening = now - timezone.timedelta(seconds=CHECKOUT_OPENING_SECONDS)
    return (
        BookOrder.objects.filter(
            item=item,
            payment__user=user,
            payment__amount=amount,
            payment__status=Payment.Status.INITIATED,
            created_at__gte=since,
            **delivery,
        )
        .filter(~Q(payment__gateway_page_url="") | Q(created_at__gte=opening))
        .select_related("payment")
        .order_by("-created_at")
        .first()
    )


def order_book(*, user, item_id, name, phone, address, zone) -> dict:
    item = book_for_sale(item_id)
    if item is None:
        raise ValidationError({"item_id": "This book is not for sale."})
    if not opens_for(user)(item.topic):
        raise ValidationError({"item_id": "This book is only for students of its courses."})
    rate = DeliveryRate.objects.filter(zone=zone).first()
    if rate is None:
        raise ValidationError({"zone": "Delivery to this area is not set up."})
    amount = item.price + rate.charge
    if amount < MIN_AMOUNT:
        raise ValidationError({"item_id": f"The amount to pay must be at least {MIN_AMOUNT} BDT."})
    delivery = {"name": name, "phone": phone, "address": address, "zone": zone}

    with transaction.atomic():
        lock_buyer(user.pk)
        pending = _open_order(user, item, amount, delivery)
        if pending is not None and not pending.payment.gateway_page_url:
            raise ValidationError({"item_id": "This checkout is already opening. Please wait a moment."})
        if pending is not None:
            return {
                "transaction_id": pending.payment.transaction_id,
                "gateway_page_url": pending.payment.gateway_page_url,
            }
        throttle_initiate(user)
        payment = Payment.objects.create(user=user, amount=amount)
        BookOrder.objects.create(
            payment=payment, item=item, title=item.title, book_price=item.price, delivery_charge=rate.charge, **delivery
        )

    goods = {
        "product_name": item.title[:255],
        "product_category": "book",
        "product_profile": "physical-goods",
        "cus_name": name,
        "cus_phone": phone,
        "cus_add1": address[:255],
        "cus_city": DeliveryRate.Zone(zone).label,
    }
    return open_gateway_session(payment, goods=goods)
