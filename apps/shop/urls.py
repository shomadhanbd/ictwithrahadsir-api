from rest_framework.routers import DefaultRouter

from django.urls import path

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("admin/product", views.AdminProductViewSet, basename="admin-product")

urlpatterns = [
    path("products", views.public_product_list),
    path("cart", views.cart),
    path("cart/add-remove", views.cart_add_remove),
    path("cart/delete/<int:product_id>", views.cart_delete),
    path("free-course-purchase", views.free_course_purchase),
    path("order", views.create_order),
    path("payment", views.submit_payment),
    path("orders", views.my_orders),
    path("admin/payment", views.admin_payment_list),
    path("admin/payment/<int:pk>", views.admin_payment_update),
] + router.urls
