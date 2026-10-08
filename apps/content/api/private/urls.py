from django.urls import path

from apps.content.api.private.views import (
    AdminAdvertisementDetailAPIView,
    AdminAdvertisementListCreateAPIView,
    AdminPageListAPIView,
    AdminPageUpdateAPIView,
    AdminTestimonialDetailAPIView,
    AdminTestimonialListCreateAPIView,
)

urlpatterns = [
    path('pages/', AdminPageListAPIView.as_view(), name='admin_page_list'),
    path('pages/<slug:slug>/', AdminPageUpdateAPIView.as_view(), name='admin_page_update'),
    path('testimonials/', AdminTestimonialListCreateAPIView.as_view(), name='admin_testimonial_list'),
    path('testimonials/<int:pk>/', AdminTestimonialDetailAPIView.as_view(), name='admin_testimonial_detail'),
    path('advertisements/', AdminAdvertisementListCreateAPIView.as_view(), name='admin_advertisement_list'),
    path('advertisements/<int:pk>/', AdminAdvertisementDetailAPIView.as_view(), name='admin_advertisement_detail'),
]
