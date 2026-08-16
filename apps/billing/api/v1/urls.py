from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.billing.api.v1.views import (
    AdminPaymentListAPIView,
    AdminPaymentUpdateAPIView,
    AdminProductViewSet,
    CartAPIView,
    CartItemAPIView,
    CartItemDetailAPIView,
    FreeEnrollmentAPIView,
    OrderAPIView,
    PaymentSubmitAPIView,
    PublicProductListAPIView,
)

app_name = 'v1'

router = SimpleRouter()
router.register('admin/products', AdminProductViewSet, basename='admin-product')

urlpatterns = [
    path('products/', PublicProductListAPIView.as_view(), name='product_list'),
    # The cart holds items, so adding and removing act on the items rather
    # than on paths called add-remove and delete/<id>.
    path('cart/', CartAPIView.as_view(), name='cart'),
    path('cart/items/', CartItemAPIView.as_view(), name='cart_item_add'),
    path('cart/items/<int:product_id>/', CartItemDetailAPIView.as_view(), name='cart_item_detail'),
    # One collection: GET lists the caller's orders, POST places one. The
    # legacy API split these across singular `order` and plural `orders`.
    path('orders/', OrderAPIView.as_view(), name='orders'),
    path('payments/', PaymentSubmitAPIView.as_view(), name='payment_submit'),
    # Claiming a free course creates an enrolment; it is not a "purchase".
    path('enrollments/free/', FreeEnrollmentAPIView.as_view(), name='free_enrollment'),
    path('admin/payments/', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('admin/payments/<int:pk>/', AdminPaymentUpdateAPIView.as_view(), name='admin_payment_update'),
] + router.urls
