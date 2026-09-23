"""Catalogue browsing and the basket.

Checkout itself lives in `billing` -- nothing here creates an Order.
"""

from apps.core.api.permissions import IsContentStaff
from apps.core.api.viewsets import AdminModelViewSet
from apps.store.api.serializers import (
    ProductSerializer,
)
from apps.store.models import Product


class AdminProductViewSet(AdminModelViewSet):
    """Not present in the current admin-panel UI yet, but added so the shop
    actually has a management surface -- an industry-standard API shouldn't
    leave `Product` writable only via direct DB access."""

    permission_classes = [IsContentStaff]

    # `categories` is a m2m on the serializer: one query per product without it.
    queryset = Product.objects.with_categories()
    serializer_class = ProductSerializer
    lookup_field = 'slug'
