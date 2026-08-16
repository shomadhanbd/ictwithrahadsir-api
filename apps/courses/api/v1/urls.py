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

app_name = 'v1'

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
    path('courses', PublicCourseListAPIView.as_view(), name='course_list'),
    path('courses/<slug:slug>', PublicCourseDetailAPIView.as_view(), name='course_detail'),
    path('course-category', PublicCourseCategoryListAPIView.as_view(), name='course_category_list'),
    path('content/<slug:slug>', ContentDetailAPIView.as_view(), name='content_detail'),
    path('content/<slug:slug>/pdf', ContentPdfAPIView.as_view(), name='content_pdf'),
    path('my-course', MyCourseListAPIView.as_view(), name='my_course_list'),
    # Admin
    path('admin/content/toggle/<int:pk>', AdminContentToggleAPIView.as_view(), name='admin_content_toggle'),
    path('admin/course/<int:pk>/users', AdminCourseEnrolledUserListAPIView.as_view(), name='admin_course_users'),
    path('admin/course/<int:pk>/users/import', AdminCourseUserImportAPIView.as_view(), name='admin_course_user_import'),
    path('admin/course/user-attach', AdminCourseUserAttachAPIView.as_view(), name='admin_course_user_attach'),
    path('admin/course/user-update', AdminCourseUserUpdateAPIView.as_view(), name='admin_course_user_update'),
    path('admin/course/user-remove', AdminCourseUserRemoveAPIView.as_view(), name='admin_course_user_remove'),
] + router.urls
