from django.urls import path

from apps.materials.api.public.views import BookOrderAPIView, DeliveryRateListAPIView, MaterialLibraryAPIView

urlpatterns = [
    path("materials/library/", MaterialLibraryAPIView.as_view(), name="library"),
    path("materials/delivery-rates/", DeliveryRateListAPIView.as_view(), name="delivery_rate_list"),
    path("materials/book-orders/", BookOrderAPIView.as_view(), name="book_order"),
]
