from django.urls import path

from apps.materials.api.private.views import (
    AdminBookOrderListAPIView,
    AdminCategoryDetailAPIView,
    AdminCategoryListCreateAPIView,
    AdminDeliveryRateDetailAPIView,
    AdminDeliveryRateListAPIView,
    AdminItemCreateAPIView,
    AdminItemDetailAPIView,
    AdminItemMoveAPIView,
    AdminTopicDetailAPIView,
    AdminTopicListCreateAPIView,
)

urlpatterns = [
    path("materials/categories/", AdminCategoryListCreateAPIView.as_view(), name="admin_category_list"),
    path("materials/categories/<int:pk>/", AdminCategoryDetailAPIView.as_view(), name="admin_category_detail"),
    path("materials/topics/", AdminTopicListCreateAPIView.as_view(), name="admin_topic_list"),
    path("materials/topics/<int:pk>/", AdminTopicDetailAPIView.as_view(), name="admin_topic_detail"),
    path("materials/items/", AdminItemCreateAPIView.as_view(), name="admin_item_create"),
    path("materials/items/<int:pk>/", AdminItemDetailAPIView.as_view(), name="admin_item_detail"),
    path("materials/items/<int:pk>/move/", AdminItemMoveAPIView.as_view(), name="admin_item_move"),
    path("materials/book-orders/", AdminBookOrderListAPIView.as_view(), name="admin_book_order_list"),
    path("materials/delivery-rates/", AdminDeliveryRateListAPIView.as_view(), name="admin_delivery_rate_list"),
    path(
        "materials/delivery-rates/<str:zone>/",
        AdminDeliveryRateDetailAPIView.as_view(),
        name="admin_delivery_rate_detail",
    ),
]
