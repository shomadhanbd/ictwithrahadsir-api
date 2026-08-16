from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.content.api.v1.views import (
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
    path('notices/', PublicNoticeListAPIView.as_view(), name='notice_list'),
    path('notice-categories/', PublicNoticeCategoryListAPIView.as_view(), name='notice_category_list'),
    path('pages/<slug:key>/', PublicPageDetailAPIView.as_view(), name='page_detail'),
    # `contact-us` was the name of a page; this is a collection of messages.
    path('contact-messages/', ContactUsAPIView.as_view(), name='contact_messages'),
    # Admin
    path('admin/course-materials/', AdminCourseMaterialListAPIView.as_view(), name='admin_course_materials'),
    path('admin/contact-messages/', AdminContactListAPIView.as_view(), name='admin_contact_list'),
    # Marking as read acts on the message, so the id leads and the action
    # follows -- the legacy path was `admin/toggle-contact/<id>`.
    path(
        'admin/contact-messages/<int:pk>/read/',
        AdminContactToggleReadAPIView.as_view(),
        name='admin_contact_toggle_read',
    ),
    path(
        'admin/contact-messages/<int:pk>/',
        AdminContactDetailAPIView.as_view(),
        name='admin_contact_detail',
    ),
    path('admin/pages/', AdminPageListAPIView.as_view(), name='admin_page_list'),
    path('admin/pages/<slug:slug>/', AdminPageUpdateAPIView.as_view(), name='admin_page_update'),
] + router.urls
