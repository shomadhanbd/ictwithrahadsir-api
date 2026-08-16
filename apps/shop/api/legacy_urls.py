"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.shop.api.v1.views import (
    AdminPaymentListAPIView,
    AdminPaymentUpdateAPIView,
    AdminProductViewSet,
    CartAPIView,
    CartAddRemoveAPIView,
    CartDeleteAPIView,
    FreeCoursePurchaseAPIView,
    MyOrderListAPIView,
    OrderCreateAPIView,
    PaymentSubmitAPIView,
    PublicProductListAPIView,
)


router = SimpleRouter(trailing_slash=False)
router.register('admin/product', AdminProductViewSet, basename='admin-product')

urlpatterns = [
    path('products', PublicProductListAPIView.as_view()),
    path('cart', CartAPIView.as_view()),
    path('cart/add-remove', CartAddRemoveAPIView.as_view()),
    path('cart/delete/<int:product_id>', CartDeleteAPIView.as_view()),
    path('free-course-purchase', FreeCoursePurchaseAPIView.as_view()),
    path('order', OrderCreateAPIView.as_view()),
    path('payment', PaymentSubmitAPIView.as_view()),
    path('orders', MyOrderListAPIView.as_view()),
    path('admin/payment', AdminPaymentListAPIView.as_view()),
    path('admin/payment/<int:pk>', AdminPaymentUpdateAPIView.as_view()),
] + router.urls
