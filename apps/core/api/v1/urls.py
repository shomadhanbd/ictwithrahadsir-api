from django.urls import include, path

from apps.core.api.v1.views import (
    AdminDashboardAPIView,
    AdminDashboardPaymentChartAPIView,
    AdminDashboardSalesOverviewAPIView,
    SmsBalanceAPIView,
    UploadUrlRequestAPIView,
)

app_name = 'v1'

urlpatterns = [
    # `aws-upload-url` named a vendor the project does not necessarily use --
    # storage is DigitalOcean Spaces here, and the endpoint works with local
    # disk too.
    path('uploads/signed-url/', UploadUrlRequestAPIView.as_view(), name='upload_url_request'),
    path(
        'admin/',
        include(
            [
                path('dashboard/', AdminDashboardAPIView.as_view(), name='admin_dashboard'),
                path(
                    'dashboard/sales-overview/',
                    AdminDashboardSalesOverviewAPIView.as_view(),
                    name='admin_dashboard_sales_overview',
                ),
                path(
                    'dashboard/payment-chart/',
                    AdminDashboardPaymentChartAPIView.as_view(),
                    name='admin_dashboard_payment_chart',
                ),
                path('sms-balance/', SmsBalanceAPIView.as_view(), name='sms_balance'),
            ]
        ),
    ),
]
