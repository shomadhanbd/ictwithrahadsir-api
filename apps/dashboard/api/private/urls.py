from django.urls import path

from apps.dashboard.api.private.views import DashboardSummaryAPIView, PaymentChartAPIView, SalesOverviewAPIView

urlpatterns = [
    path('dashboard/', DashboardSummaryAPIView.as_view(), name='admin_dashboard'),
    path('dashboard/sales-overview/', SalesOverviewAPIView.as_view(), name='admin_dashboard_sales'),
    path('dashboard/payment-chart/', PaymentChartAPIView.as_view(), name='admin_dashboard_payments'),
]
