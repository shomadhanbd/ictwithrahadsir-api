from django.urls import path

from apps.billing.api.private.views import AdminPaymentListAPIView, AdminPaymentUpdateAPIView

urlpatterns = [
    path('payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('payments/<int:pk>/', AdminPaymentUpdateAPIView.as_view(), name='admin_payment_update'),
]
