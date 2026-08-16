"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from django.urls import path

from apps.core.api.v1.views import (
    AdminDashboardAPIView,
    AdminDashboardPaymentChartAPIView,
    AdminDashboardSalesOverviewAPIView,
    SmsBalanceAPIView,
    UploadUrlRequestAPIView,
)


urlpatterns = [
    path('aws-upload-url', UploadUrlRequestAPIView.as_view()),
    path('admin/dashboard', AdminDashboardAPIView.as_view()),
    path(
        'admin/dashboard/sales-overview',
        AdminDashboardSalesOverviewAPIView.as_view(),
    ),
    path(
        'admin/dashboard/payment-chart',
        AdminDashboardPaymentChartAPIView.as_view(),
    ),
    path('admin/sms-balance', SmsBalanceAPIView.as_view()),
]
