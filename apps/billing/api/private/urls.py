from django.urls import include, path

from apps.billing.api.private.views import (
    AdminDashboardAPIView,
    AdminDashboardPaymentChartAPIView,
    AdminDashboardSalesOverviewAPIView,
    AdminPaymentListAPIView,
    AdminPaymentUpdateAPIView,
)

#: No `app_name` -- see the note in the sibling `public/urls.py`.
urlpatterns = [
    path('payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('payments/<int:pk>/', AdminPaymentUpdateAPIView.as_view(), name='admin_payment_update'),
    # The admin dashboard is mostly order and revenue aggregation, so it
    # belongs to the app that owns those rows rather than to core.
    path(
        'dashboard/',
        include(
            [
                path('', AdminDashboardAPIView.as_view(), name='admin_dashboard'),
                path(
                    'sales-overview/',
                    AdminDashboardSalesOverviewAPIView.as_view(),
                    name='admin_dashboard_sales_overview',
                ),
                path(
                    'payment-chart/',
                    AdminDashboardPaymentChartAPIView.as_view(),
                    name='admin_dashboard_payment_chart',
                ),
            ]
        ),
    ),
]
