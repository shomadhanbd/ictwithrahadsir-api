from rest_framework.routers import SimpleRouter

from django.urls import include, path

from apps.courses.api.v1.views import (
    AdminContentToggleAPIView,
    AdminContentViewSet,
    AdminCourseCategoryViewSet,
    AdminCourseEnrolledUserListAPIView,
    AdminCoursePriceViewSet,
    AdminCourseUserImportAPIView,
    AdminCourseViewSet,
    AdminEnrollmentAPIView,
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

router = SimpleRouter()
router.register('admin/course-categories', AdminCourseCategoryViewSet, basename='admin-course-category')
router.register('admin/instructors', AdminInstructorViewSet, basename='admin-instructor')
router.register('admin/prices', AdminCoursePriceViewSet, basename='admin-price')
router.register('admin/coupons', AdminCouponViewSet, basename='admin-coupon')
router.register('admin/routines', AdminRoutineViewSet, basename='admin-routine')
router.register('admin/sections', AdminSectionViewSet, basename='admin-section')
router.register('admin/contents', AdminContentViewSet, basename='admin-content')
router.register('admin/courses', AdminCourseViewSet, basename='admin-course')

urlpatterns = [
    # Public
    path('courses/', PublicCourseListAPIView.as_view(), name='course_list'),
    path('courses/<slug:slug>/', PublicCourseDetailAPIView.as_view(), name='course_detail'),
    path('course-categories/', PublicCourseCategoryListAPIView.as_view(), name='course_category_list'),
    path('contents/<slug:slug>/', ContentDetailAPIView.as_view(), name='content_detail'),
    path('contents/<slug:slug>/pdf/', ContentPdfAPIView.as_view(), name='content_pdf'),
    # Scoped to the caller, so it hangs off /me/ like the profile does.
    path('me/courses/', MyCourseListAPIView.as_view(), name='my_course_list'),
    # Admin. Explicit routes come before the routers so a literal segment is
    # never mistaken for a detail lookup.
    path(
        'admin/contents/<int:pk>/toggle/',
        AdminContentToggleAPIView.as_view(),
        name='admin_content_toggle',
    ),
    path(
        'admin/courses/<int:pk>/enrollments/',
        AdminCourseEnrolledUserListAPIView.as_view(),
        name='admin_course_users',
    ),
    path(
        'admin/courses/<int:pk>/enrollments/import/',
        AdminCourseUserImportAPIView.as_view(),
        name='admin_course_user_import',
    ),
    # One resource, a method per action: POST attaches, PATCH amends, DELETE
    # removes. Replaces the three POST-only endpoints the legacy API called
    # user-attach / user-update / user-remove.
    path('admin/enrollments/', AdminEnrollmentAPIView.as_view(), name='admin_enrollment'),
] + router.urls
