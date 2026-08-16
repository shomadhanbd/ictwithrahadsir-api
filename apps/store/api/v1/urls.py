from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.store.api.v1.views import (
    AdminProductViewSet,
    CartAPIView,
    CartItemAPIView,
    CartItemDetailAPIView,
    PublicProductListAPIView,
)

app_name = 'v1'

router = SimpleRouter()
router.register('admin/products', AdminProductViewSet, basename='admin-product')

urlpatterns = [
    path('products/', PublicProductListAPIView.as_view(), name='product_list'),
    # The cart holds items, so adding and removing act on the items.
    path('cart/', CartAPIView.as_view(), name='cart'),
    path('cart/items/', CartItemAPIView.as_view(), name='cart_item_add'),
    path('cart/items/<int:product_id>/', CartItemDetailAPIView.as_view(), name='cart_item_detail'),
] + router.urls
