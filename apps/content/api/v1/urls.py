from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.content.api.v1.views import (
    AdminAdvertisementViewSet,
    AdminEBookViewSet,
    AdminNoticeCategoryViewSet,
    AdminNoticeViewSet,
    AdminPageListAPIView,
    AdminPageUpdateAPIView,
    AdminTestimonialViewSet,
    HomeAPIView,
    PublicEBookListAPIView,
    PublicNoticeCategoryListAPIView,
    PublicNoticeListAPIView,
    PublicPageDetailAPIView,
)

app_name = 'v1'

router = SimpleRouter()
router.register('admin/notice-categories', AdminNoticeCategoryViewSet, basename='admin-notice-category')
router.register('admin/testimonials', AdminTestimonialViewSet, basename='admin-testimonial')
router.register('admin/advertisements', AdminAdvertisementViewSet, basename='admin-advertisement')
# "exclusive" was marketing copy; the model is an EBook.
router.register('admin/ebooks', AdminEBookViewSet, basename='admin-exclusive-ebook')
router.register('admin/notices', AdminNoticeViewSet, basename='admin-notice')

urlpatterns = [
    # Public
    path('home/', HomeAPIView.as_view(), name='home'),
    path('ebooks/', PublicEBookListAPIView.as_view(), name='ebook_list'),
    path('notices/', PublicNoticeListAPIView.as_view(), name='notice_list'),
    path('notice-categories/', PublicNoticeCategoryListAPIView.as_view(), name='notice_category_list'),
    path('pages/<slug:key>/', PublicPageDetailAPIView.as_view(), name='page_detail'),
    # Admin
    path('admin/pages/', AdminPageListAPIView.as_view(), name='admin_page_list'),
    path('admin/pages/<slug:slug>/', AdminPageUpdateAPIView.as_view(), name='admin_page_update'),
] + router.urls
