from rest_framework.routers import DefaultRouter

from django.urls import path

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("admin/notice-category", views.AdminNoticeCategoryViewSet, basename="admin-notice-category")
router.register("admin/testimonial", views.AdminTestimonialViewSet, basename="admin-testimonial")
router.register("admin/advertisement", views.AdminAdvertisementViewSet, basename="admin-advertisement")
router.register("admin/exclusive-ebook", views.AdminEBookViewSet, basename="admin-exclusive-ebook")
router.register("admin/notice", views.AdminNoticeViewSet, basename="admin-notice")

urlpatterns = [
    # Public
    path("home", views.home),
    path("notices", views.public_notice_list),
    path("notice-category", views.public_notice_category_list),
    path("page/<slug:key>", views.public_page_detail),
    path("contact-us", views.contact_us),
    # Admin
    path("admin/course-materials", views.admin_course_materials),
    path("admin/contact", views.admin_contact_list),
    path("admin/toggle-contact/<int:pk>", views.admin_contact_toggle_read),
    path("admin/contact/<int:pk>", views.admin_contact_detail),
    path("admin/page", views.admin_page_list),
    path("admin/page/<slug:slug>", views.admin_page_update),
] + router.urls
