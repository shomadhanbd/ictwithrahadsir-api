from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.shop.api.v1.views import (
    AdminPaymentListAPIView,
    AdminPaymentUpdateAPIView,
    AdminProductViewSet,
    CartAPIView,
    CartAddRemoveAPIView,
    CartDeleteAPIView,
    FreeCoursePurchaseAPIView,
    MyOrderListAPIView,
    OrderCreateAPIView,
    PaymentSubmitAPIView,
    PublicProductListAPIView,
)

app_name = 'v1'

router = SimpleRouter(trailing_slash=False)
router.register('admin/product', AdminProductViewSet, basename='admin-product')

urlpatterns = [
    path('products', PublicProductListAPIView.as_view(), name='product_list'),
    path('cart', CartAPIView.as_view(), name='cart'),
    path('cart/add-remove', CartAddRemoveAPIView.as_view(), name='cart_add_remove'),
    path('cart/delete/<int:product_id>', CartDeleteAPIView.as_view(), name='cart_delete'),
    path('free-course-purchase', FreeCoursePurchaseAPIView.as_view(), name='free_course_purchase'),
    path('order', OrderCreateAPIView.as_view(), name='order_create'),
    path('payment', PaymentSubmitAPIView.as_view(), name='payment_submit'),
    path('orders', MyOrderListAPIView.as_view(), name='my_order_list'),
    path('admin/payment', AdminPaymentListAPIView.as_view(), name='admin_payment_list'),
    path('admin/payment/<int:pk>', AdminPaymentUpdateAPIView.as_view(), name='admin_payment_update'),
] + router.urls
