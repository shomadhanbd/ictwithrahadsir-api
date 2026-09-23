from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.billing.api.private.views import (
    AdminOrderListAPIView,
    AdminPaymentListAPIView,
    AdminPaymentUpdateAPIView,
    AdminProductCouponViewSet,
    AdminProductViewSet,
)

router = SimpleRouter()
router.register('products', AdminProductViewSet, basename='admin-product')
router.register('product-coupons', AdminProductCouponViewSet, basename='admin-product-coupon')

urlpatterns = [
    path('orders/', AdminOrderListAPIView.as_view(), name='admin_order_list'),
    path('payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('payments/<int:pk>/', AdminPaymentUpdateAPIView.as_view(), name='admin_payment_update'),
] + router.urls
