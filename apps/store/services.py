"""Basket operations.

Checkout is not here -- `billing` owns orders. This is only the basket the
customer fills before getting there.

Quantity changes go through `select_for_update` for the same reason the
stock reservation in `billing` does: read-modify-write on a counter loses an
update when two requests arrive together, and "add to cart" is exactly the
kind of button people double-click.
"""

from django.db import transaction

from rest_framework.exceptions import NotFound, ValidationError

from apps.store.models import CartItem, Product


def cart_items_for(user):
    """The caller's whole basket, ready to serialise.

    The nested product carries its categories, so those are prefetched too --
    otherwise the cart costs a query per line just for them.
    """
    return CartItem.objects.for_user(user).with_product()


@transaction.atomic
def add_to_cart(*, user, product_id) -> CartItem:
    """Put a product in the basket, or add one to a line already there."""
    product = Product.objects.active().filter(pk=product_id).first()
    if not product:
        raise ValidationError({'product_id': ['Product not found.']})

    item, created = CartItem.objects.get_or_create(user=user, product=product)
    if not created:
        locked = CartItem.objects.select_for_update().get(pk=item.pk)
        locked.quantity += 1
        locked.save(update_fields=['quantity'])
        return locked
    return item


@transaction.atomic
def adjust_cart_quantity(*, user, product_id, action: str) -> None:
    """Step a basket line up or down; a line stepped to zero is removed."""
    item = (
        CartItem.objects.select_for_update().for_user(user).filter(product_id=product_id).first()
    )
    if not item:
        raise NotFound('Item is not in the cart.')

    if action == 'increment':
        item.quantity += 1
        item.save(update_fields=['quantity'])
    elif action == 'decrement':
        item.quantity -= 1
        if item.quantity <= 0:
            item.delete()
        else:
            item.save(update_fields=['quantity'])
    else:
        raise ValidationError({'action': ['Must be `increment` or `decrement`.']})


def remove_from_cart(*, user, product_id) -> None:
    CartItem.objects.for_user(user).filter(product_id=product_id).delete()
