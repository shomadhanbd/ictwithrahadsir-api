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

app_name = 'v1'

router = SimpleRouter(trailing_slash=False)
router.register('admin/notice-category', AdminNoticeCategoryViewSet, basename='admin-notice-category')
router.register('admin/testimonial', AdminTestimonialViewSet, basename='admin-testimonial')
router.register('admin/advertisement', AdminAdvertisementViewSet, basename='admin-advertisement')
router.register('admin/exclusive-ebook', AdminEBookViewSet, basename='admin-exclusive-ebook')
router.register('admin/notice', AdminNoticeViewSet, basename='admin-notice')

urlpatterns = [
    # Public
    path('home', HomeAPIView.as_view(), name='home'),
    path('notices', PublicNoticeListAPIView.as_view(), name='notice_list'),
    path('notice-category', PublicNoticeCategoryListAPIView.as_view(), name='notice_category_list'),
    path('page/<slug:key>', PublicPageDetailAPIView.as_view(), name='page_detail'),
    path('contact-us', ContactUsAPIView.as_view(), name='contact_us'),
    # Admin
    path('admin/course-materials', AdminCourseMaterialListAPIView.as_view(), name='admin_course_materials'),
    path('admin/contact', AdminContactListAPIView.as_view(), name='admin_contact_list'),
    path('admin/toggle-contact/<int:pk>', AdminContactToggleReadAPIView.as_view(), name='admin_contact_toggle_read'),
    path('admin/contact/<int:pk>', AdminContactDetailAPIView.as_view(), name='admin_contact_detail'),
    path('admin/page', AdminPageListAPIView.as_view(), name='admin_page_list'),
    path('admin/page/<slug:slug>', AdminPageUpdateAPIView.as_view(), name='admin_page_update'),
] + router.urls
