from django.urls import path

from apps.content.api.private.views import (
    AdminAdvertisementDetailAPIView,
    AdminAdvertisementListCreateAPIView,
    AdminEBookDetailAPIView,
    AdminEBookListCreateAPIView,
    AdminNoticeCategoryDetailAPIView,
    AdminNoticeCategoryListCreateAPIView,
    AdminNoticeDetailAPIView,
    AdminNoticeListCreateAPIView,
    AdminPageListAPIView,
    AdminPageUpdateAPIView,
    AdminTestimonialDetailAPIView,
    AdminTestimonialListCreateAPIView,
)

urlpatterns = [
    path('pages/', AdminPageListAPIView.as_view(), name='admin_page_list'),
    path('pages/<slug:slug>/', AdminPageUpdateAPIView.as_view(), name='admin_page_update'),
    path('notice-categories/', AdminNoticeCategoryListCreateAPIView.as_view(), name='admin_notice_category_list'),
    path(
        'notice-categories/<int:pk>/',
        AdminNoticeCategoryDetailAPIView.as_view(),
        name='admin_notice_category_detail',
    ),
    path('testimonials/', AdminTestimonialListCreateAPIView.as_view(), name='admin_testimonial_list'),
    path('testimonials/<int:pk>/', AdminTestimonialDetailAPIView.as_view(), name='admin_testimonial_detail'),
    path('advertisements/', AdminAdvertisementListCreateAPIView.as_view(), name='admin_advertisement_list'),
    path('advertisements/<int:pk>/', AdminAdvertisementDetailAPIView.as_view(), name='admin_advertisement_detail'),
    path('ebooks/', AdminEBookListCreateAPIView.as_view(), name='admin_ebook_list'),
    path('ebooks/<int:pk>/', AdminEBookDetailAPIView.as_view(), name='admin_ebook_detail'),
    path('notices/', AdminNoticeListCreateAPIView.as_view(), name='admin_notice_list'),
    path('notices/<slug:slug>/', AdminNoticeDetailAPIView.as_view(), name='admin_notice_detail'),
]
