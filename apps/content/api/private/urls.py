from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.content.api.private.views import (
    AdminAdvertisementViewSet,
    AdminEBookViewSet,
    AdminNoticeCategoryViewSet,
    AdminNoticeViewSet,
    AdminPageListAPIView,
    AdminPageUpdateAPIView,
    AdminTestimonialViewSet,
)

router = SimpleRouter()
router.register('notice-categories', AdminNoticeCategoryViewSet, basename='admin-notice-category')
router.register('testimonials', AdminTestimonialViewSet, basename='admin-testimonial')
router.register('advertisements', AdminAdvertisementViewSet, basename='admin-advertisement')
router.register('ebooks', AdminEBookViewSet, basename='admin-exclusive-ebook')
router.register('notices', AdminNoticeViewSet, basename='admin-notice')

urlpatterns = [
    path('pages/', AdminPageListAPIView.as_view(), name='admin_page_list'),
    path('pages/<slug:slug>/', AdminPageUpdateAPIView.as_view(), name='admin_page_update'),
] + router.urls
