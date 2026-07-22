from django.urls import path, re_path

from . import dashboard, uploads

urlpatterns = [
    path("aws-upload-url", uploads.request_upload_url),
    re_path(r"^media-upload/(?P<name>.+)$", uploads.local_media_upload, name="local-media-upload"),
    path("admin/dashboard", dashboard.admin_dashboard),
    path("admin/dashboard/sales-overview", dashboard.admin_dashboard_sales_overview),
    path("admin/dashboard/payment-chart", dashboard.admin_dashboard_payment_chart),
    path("admin/sms-balance", dashboard.sms_balance),
]
