"""Catalogue browsing and the basket.

Checkout itself lives in `billing` -- nothing here creates an Order.
"""

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.viewsets import AdminModelViewSet
from apps.store.api.v1.serializers import CartItemSerializer, ProductSerializer
from apps.store.models import CartItem, Product


class AdminProductViewSet(AdminModelViewSet):
    """Not present in the current admin-panel UI yet, but added so the shop
    actually has a management surface -- an industry-standard API shouldn't
    leave `Product` writable only via direct DB access."""

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = 'slug'


# ---------------------------------------------------------------------------
# Public catalog
# ---------------------------------------------------------------------------


class PublicProductListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    pagination_class = LaravelStylePageNumberPagination
    queryset = Product.objects.filter(active=True)


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class BaseCartAPIView(APIView):
    """Every cart endpoint answers with the caller's whole cart, so the
    client never has to reconcile a partial update."""

    permission_classes = [IsAuthenticated]

    def cart_response(self):
        items = CartItem.objects.filter(user=self.request.user).select_related('product')
        return Response(CartItemSerializer(items, many=True).data)


class CartItemAPIView(BaseCartAPIView):
    """POST /cart/items/ -- put a product in the cart."""

    def post(self, request):
        product = Product.objects.filter(
            pk=request.data.get('product_id'), active=True
        ).first()
        if not product:
            raise ValidationError({'product_id': ['Product not found.']})

        item, created = CartItem.objects.get_or_create(user=request.user, product=product)
        if not created:
            item.quantity += 1
            item.save(update_fields=['quantity'])
        return self.cart_response()


class CartAPIView(CartItemAPIView):
    """GET /cart/ -- the caller's cart.

    Inherits POST so the legacy `POST /cart` add still works.
    """

    def get(self, request):
        return self.cart_response()


class CartItemDetailAPIView(BaseCartAPIView):
    """One line in the cart: PATCH adjusts the quantity, DELETE removes it."""

    def patch(self, request, product_id):
        return self.adjust_quantity(request, product_id, request.data.get('action'))

    def delete(self, request, product_id):
        CartItem.objects.filter(user=request.user, product_id=product_id).delete()
        return self.cart_response()

    def adjust_quantity(self, request, product_id, action):
        item = CartItem.objects.filter(user=request.user, product_id=product_id).first()
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

        return self.cart_response()


class CartAddRemoveAPIView(CartItemDetailAPIView):
    """Legacy `POST /cart/add-remove` -- product id and action in the body."""

    def post(self, request):
        return self.adjust_quantity(
            request, request.data.get('product_id'), request.data.get('action')
        )


class CartDeleteAPIView(CartItemDetailAPIView):
    """Legacy `DELETE /cart/delete/<product_id>`."""
