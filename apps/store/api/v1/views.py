"""Catalogue browsing and the basket.

Checkout itself lives in `billing` -- nothing here creates an Order.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsContentStaff
from apps.core.api.viewsets import AdminModelViewSet
from apps.store.api.v1.serializers import (
    CartAddRequestSerializer,
    CartItemSerializer,
    CartQuantityRequestSerializer,
    ProductSerializer,
)
from apps.store.models import Product
from apps.store.services import (
    add_to_cart,
    adjust_cart_quantity,
    cart_items_for,
    remove_from_cart,
)


class AdminProductViewSet(AdminModelViewSet):
    """Not present in the current admin-panel UI yet, but added so the shop
    actually has a management surface -- an industry-standard API shouldn't
    leave `Product` writable only via direct DB access."""
    permission_classes = [IsContentStaff]

    # `categories` is a m2m on the serializer: one query per product without it.
    queryset = Product.objects.with_categories()
    serializer_class = ProductSerializer
    lookup_field = 'slug'


# ---------------------------------------------------------------------------
# Public catalog
# ---------------------------------------------------------------------------


class PublicProductListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    pagination_class = LaravelStylePageNumberPagination
    queryset = Product.objects.active().with_categories()


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class BaseCartAPIView(APIView):
    """Every cart endpoint answers with the caller's whole cart, so the
    client never has to reconcile a partial update."""

    permission_classes = [IsAuthenticated]

    def cart_response(self):
        items = cart_items_for(self.request.user)
        return Response(CartItemSerializer(items, many=True).data)


class CartItemAPIView(BaseCartAPIView):
    """POST /cart/items/ -- put a product in the cart."""

    @extend_schema(
        summary='Add a product to the cart',
        request=CartAddRequestSerializer,
        responses={200: CartItemSerializer(many=True)},
    )
    def post(self, request):
        serializer = CartAddRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        add_to_cart(user=request.user, **serializer.validated_data)
        return self.cart_response()


class CartAPIView(CartItemAPIView):
    """GET /cart/ -- the caller's cart.

    Inherits POST so the legacy `POST /cart` add still works.
    """

    @extend_schema(summary="The caller's cart", responses={200: CartItemSerializer(many=True)})
    def get(self, request):
        return self.cart_response()


class CartItemDetailAPIView(BaseCartAPIView):
    """One line in the cart: PATCH adjusts the quantity, DELETE removes it."""

    @extend_schema(
        summary='Increment or decrement a cart line',
        request=CartQuantityRequestSerializer,
        responses={200: CartItemSerializer(many=True)},
    )
    def patch(self, request, product_id):
        serializer = CartQuantityRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adjust_cart_quantity(
            user=request.user, product_id=product_id, **serializer.validated_data
        )
        return self.cart_response()

    @extend_schema(summary='Remove a cart line', responses={200: CartItemSerializer(many=True)})
    def delete(self, request, product_id):
        remove_from_cart(user=request.user, product_id=product_id)
        return self.cart_response()
