"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.courses.api.v1.views import (
    AdminContentToggleAPIView,
    AdminContentViewSet,
    AdminCourseCategoryViewSet,
    AdminCourseEnrolledUserListAPIView,
    AdminCoursePriceViewSet,
    AdminCourseUserAttachAPIView,
    AdminCourseUserImportAPIView,
    AdminCourseUserRemoveAPIView,
    AdminCourseUserUpdateAPIView,
    AdminCourseViewSet,
    AdminCouponViewSet,
    AdminInstructorViewSet,
    AdminRoutineViewSet,
    AdminSectionViewSet,
    ContentDetailAPIView,
    ContentPdfAPIView,
    MyCourseListAPIView,
    PublicCourseCategoryListAPIView,
    PublicCourseDetailAPIView,
    PublicCourseListAPIView,
)


router = SimpleRouter(trailing_slash=False)
router.register('admin/course-category', AdminCourseCategoryViewSet, basename='admin-course-category')
router.register('admin/instructor', AdminInstructorViewSet, basename='admin-instructor')
router.register('admin/price', AdminCoursePriceViewSet, basename='admin-price')
router.register('admin/coupon', AdminCouponViewSet, basename='admin-coupon')
router.register('admin/routine', AdminRoutineViewSet, basename='admin-routine')
router.register('admin/section', AdminSectionViewSet, basename='admin-section')
router.register('admin/content', AdminContentViewSet, basename='admin-content')
router.register('admin/course', AdminCourseViewSet, basename='admin-course')

urlpatterns = [
    # Public
    path('courses', PublicCourseListAPIView.as_view()),
    path('courses/<slug:slug>', PublicCourseDetailAPIView.as_view()),
    path('course-category', PublicCourseCategoryListAPIView.as_view()),
    path('content/<slug:slug>', ContentDetailAPIView.as_view()),
    path('content/<slug:slug>/pdf', ContentPdfAPIView.as_view()),
    path('my-course', MyCourseListAPIView.as_view()),
    # Admin
    path('admin/content/toggle/<int:pk>', AdminContentToggleAPIView.as_view()),
    path('admin/course/<int:pk>/users', AdminCourseEnrolledUserListAPIView.as_view()),
    path('admin/course/<int:pk>/users/import', AdminCourseUserImportAPIView.as_view()),
    path('admin/course/user-attach', AdminCourseUserAttachAPIView.as_view()),
    path('admin/course/user-update', AdminCourseUserUpdateAPIView.as_view()),
    path('admin/course/user-remove', AdminCourseUserRemoveAPIView.as_view()),
] + router.urls
