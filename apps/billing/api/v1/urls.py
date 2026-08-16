from django.urls import include, path

from apps.billing.api.v1.views import (
    AdminDashboardAPIView,
    AdminDashboardPaymentChartAPIView,
    AdminDashboardSalesOverviewAPIView,
    AdminPaymentListAPIView,
    AdminPaymentUpdateAPIView,
    FreeEnrollmentAPIView,
    OrderAPIView,
    PaymentSubmitAPIView,
)

app_name = 'v1'

urlpatterns = [
    # One collection: GET lists the caller's orders, POST places one.
    path('orders/', OrderAPIView.as_view(), name='orders'),
    path('payments/', PaymentSubmitAPIView.as_view(), name='payment_submit'),
    # Claiming a free course creates an enrolment; it is not a "purchase".
    path('enrollments/free/', FreeEnrollmentAPIView.as_view(), name='free_enrollment'),
    path('admin/payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('admin/payments/<int:pk>/', AdminPaymentUpdateAPIView.as_view(), name='admin_payment_update'),
    # The admin dashboard is mostly order and revenue aggregation, so it
    # belongs to the app that owns those rows rather than to core.
    path(
        'admin/dashboard/',
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
