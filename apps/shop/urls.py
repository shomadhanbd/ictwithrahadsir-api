from rest_framework.routers import SimpleRouter

from django.urls import path

from . import views

# SimpleRouter, not DefaultRouter: every app mounts its own router under
# the same /api prefix, so six DefaultRouters each registered an
# `api-root` view at /api/ and only the first-loaded one ever matched --
# the index advertised one app's routes and hid the other five. Nothing
# consumes the index or the generated `.json` suffix routes.
router = SimpleRouter(trailing_slash=False)
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
