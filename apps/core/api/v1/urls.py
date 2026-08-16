from django.urls import path, re_path

from apps.core.api.v1.views import (
    AdminDashboardAPIView,
    AdminDashboardPaymentChartAPIView,
    AdminDashboardSalesOverviewAPIView,
    LocalMediaUploadView,
    SmsBalanceAPIView,
    UploadUrlRequestAPIView,
)

app_name = 'v1'

urlpatterns = [
    path('aws-upload-url', UploadUrlRequestAPIView.as_view(), name='upload_url_request'),
    # re_path because the object key may contain slashes ("<folder>/<file>.png"),
    # which a <str:> converter would refuse to match.
    re_path(
        r'^media-upload/(?P<name>.+)$',
        LocalMediaUploadView.as_view(),
        name='local_media_upload',
    ),
    path('admin/dashboard', AdminDashboardAPIView.as_view(), name='admin_dashboard'),
    path(
        'admin/dashboard/sales-overview',
        AdminDashboardSalesOverviewAPIView.as_view(),
        name='admin_dashboard_sales_overview',
    ),
    path(
        'admin/dashboard/payment-chart',
        AdminDashboardPaymentChartAPIView.as_view(),
        name='admin_dashboard_payment_chart',
    ),
    path('admin/sms-balance', SmsBalanceAPIView.as_view(), name='sms_balance'),
]
