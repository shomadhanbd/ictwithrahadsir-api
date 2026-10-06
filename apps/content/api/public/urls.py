from django.urls import path

from apps.content.api.public.views import (
    HomeAPIView,
    PublicEBookListAPIView,
    PublicNoticeCategoryListAPIView,
    PublicNoticeListAPIView,
    PublicPageDetailAPIView,
)

urlpatterns = [
    path('home/', HomeAPIView.as_view(), name='home'),
    path('ebooks/', PublicEBookListAPIView.as_view(), name='ebook_list'),
    path('notices/', PublicNoticeListAPIView.as_view(), name='notice_list'),
    path('notice-categories/', PublicNoticeCategoryListAPIView.as_view(), name='notice_category_list'),
    path('pages/<slug:key>/', PublicPageDetailAPIView.as_view(), name='page_detail'),
]
