from django.urls import path

from apps.billing.api.public.views import (
    FreeEnrollmentAPIView,
    MyProductListAPIView,
    OrderAPIView,
    OrderPayAPIView,
    OrderQuoteAPIView,
    ProductDetailAPIView,
    ProductListAPIView,
    SslCommerzCancelView,
    SslCommerzFailView,
    SslCommerzIpnView,
    SslCommerzSuccessView,
)

#: No `app_name`: assembled into the app's single namespace by
#: `apps.billing.api.urls`, so route names survive the split.
urlpatterns = [
    path('products/', ProductListAPIView.as_view(), name='products'),
    path('products/<str:slug>/', ProductDetailAPIView.as_view(), name='product_detail'),
    path('me/products/', MyProductListAPIView.as_view(), name='my_products'),
    # One collection: GET lists the caller's orders, POST places one.
    path('orders/', OrderAPIView.as_view(), name='orders'),
    path('orders/quote/', OrderQuoteAPIView.as_view(), name='order_quote'),
    path('orders/<int:pk>/pay/', OrderPayAPIView.as_view(), name='order_pay'),
    # SSLCommerz posts these; see `SslCommerzCallbackView`.
    path('payments/sslcommerz/success/', SslCommerzSuccessView.as_view(), name='sslcommerz_success'),
    path('payments/sslcommerz/fail/', SslCommerzFailView.as_view(), name='sslcommerz_fail'),
    path('payments/sslcommerz/cancel/', SslCommerzCancelView.as_view(), name='sslcommerz_cancel'),
    path('payments/sslcommerz/ipn/', SslCommerzIpnView.as_view(), name='sslcommerz_ipn'),
    # Claiming a free course creates an enrolment; it is not a "purchase".
    path('enrollments/free/', FreeEnrollmentAPIView.as_view(), name='free_enrollment'),
]
