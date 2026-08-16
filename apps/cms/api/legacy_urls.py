"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.cms.api.v1.views import (
    AdminAdvertisementViewSet,
    AdminContactDetailAPIView,
    AdminContactListAPIView,
    AdminContactToggleReadAPIView,
    AdminCourseMaterialListAPIView,
    AdminEBookViewSet,
    AdminNoticeCategoryViewSet,
    AdminNoticeViewSet,
    AdminPageListAPIView,
    AdminPageUpdateAPIView,
    AdminTestimonialViewSet,
    ContactUsAPIView,
    HomeAPIView,
    PublicNoticeCategoryListAPIView,
    PublicNoticeListAPIView,
    PublicPageDetailAPIView,
)


router = SimpleRouter(trailing_slash=False)
router.register('admin/notice-category', AdminNoticeCategoryViewSet, basename='admin-notice-category')
router.register('admin/testimonial', AdminTestimonialViewSet, basename='admin-testimonial')
router.register('admin/advertisement', AdminAdvertisementViewSet, basename='admin-advertisement')
router.register('admin/exclusive-ebook', AdminEBookViewSet, basename='admin-exclusive-ebook')
router.register('admin/notice', AdminNoticeViewSet, basename='admin-notice')

urlpatterns = [
    # Public
    path('home', HomeAPIView.as_view()),
    path('notices', PublicNoticeListAPIView.as_view()),
    path('notice-category', PublicNoticeCategoryListAPIView.as_view()),
    path('page/<slug:key>', PublicPageDetailAPIView.as_view()),
    path('contact-us', ContactUsAPIView.as_view()),
    # Admin
    path('admin/course-materials', AdminCourseMaterialListAPIView.as_view()),
    path('admin/contact', AdminContactListAPIView.as_view()),
    path('admin/toggle-contact/<int:pk>', AdminContactToggleReadAPIView.as_view()),
    path('admin/contact/<int:pk>', AdminContactDetailAPIView.as_view()),
    path('admin/page', AdminPageListAPIView.as_view()),
    path('admin/page/<slug:slug>', AdminPageUpdateAPIView.as_view()),
] + router.urls
