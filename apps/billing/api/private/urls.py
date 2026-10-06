from django.urls import path

from apps.billing.api.private.views import (
    AdminCashSaleAPIView,
    AdminPaymentListAPIView,
    AdminProductDetailAPIView,
    AdminProductListCreateAPIView,
)

urlpatterns = [
    path('payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('payments/cash/', AdminCashSaleAPIView.as_view(), name='admin_cash_sale'),
    path('products/', AdminProductListCreateAPIView.as_view(), name='admin_product_list'),
    path('products/<int:pk>/', AdminProductDetailAPIView.as_view(), name='admin_product_detail'),
]
