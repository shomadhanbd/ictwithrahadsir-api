from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.billing.api.private.views import AdminCashSaleAPIView, AdminPaymentListAPIView, AdminProductViewSet

router = SimpleRouter()
router.register('products', AdminProductViewSet, basename='admin-product')

urlpatterns = [
    path('payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('payments/cash/', AdminCashSaleAPIView.as_view(), name='admin_cash_sale'),
] + router.urls
