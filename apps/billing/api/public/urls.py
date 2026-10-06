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
    path('products/', ProductListView.as_view(), name='product-list'),
    path('payments/initiate/', PaymentInitiateView.as_view(), name='payment-initiate'),
    path('payments/capture/', PaymentCaptureView.as_view(), name='payment-capture'),
    path('payments/ipn/', PaymentIPNView.as_view(), name='payment-ipn'),
    path('me/payments/', MyPaymentListView.as_view(), name='my-payments'),
    path('me/payments/<str:tran_id>/', MyPaymentDetailView.as_view(), name='my-payment-detail'),
]
