from django.urls import path

from apps.store.api.public.views import (
    CartAPIView,
    CartItemAPIView,
    CartItemDetailAPIView,
    PublicProductListAPIView,
)

#: No `app_name`: assembled into the app's single `v1` namespace by
#: `apps.store.api.urls`, so route names survive the split.
urlpatterns = [
    path('products/', PublicProductListAPIView.as_view(), name='product_list'),
    # The cart holds items, so adding and removing act on the items.
    path('cart/', CartAPIView.as_view(), name='cart'),
    path('cart/items/', CartItemAPIView.as_view(), name='cart_item_add'),
    path('cart/items/<int:product_id>/', CartItemDetailAPIView.as_view(), name='cart_item_detail'),
]
