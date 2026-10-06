from django.urls import path

from apps.billing.api.public.views import (
    MyPaymentDetailView,
    MyPaymentListView,
    PaymentCaptureView,
    PaymentInitiateView,
    PaymentIPNView,
    ProductListView,
)

urlpatterns = [
    path('products/', ProductListView.as_view(), name='product_list'),
    path('payments/initiate/', PaymentInitiateView.as_view(), name='payment_initiate'),
    path('payments/capture/', PaymentCaptureView.as_view(), name='payment_capture'),
    path('payments/ipn/', PaymentIPNView.as_view(), name='payment_ipn'),
    path('me/payments/', MyPaymentListView.as_view(), name='my_payments'),
    path('me/payments/<str:tran_id>/', MyPaymentDetailView.as_view(), name='my_payment_detail'),
]
