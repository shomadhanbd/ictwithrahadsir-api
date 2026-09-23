from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.courses.api.private.views import (
    AdminContentToggleAPIView,
    AdminContentViewSet,
    AdminCouponViewSet,
    AdminCourseCategoryViewSet,
    AdminCourseEnrolledUserListAPIView,
    AdminCourseMaterialViewSet,
    AdminCoursePriceViewSet,
    AdminCourseTeacherViewSet,
    AdminCourseViewSet,
    AdminEnrollmentAPIView,
    AdminRoutineViewSet,
    AdminSectionViewSet,
)

#: No `app_name` -- see the note in the sibling `public/urls.py`.
router = SimpleRouter()
router.register('course-categories', AdminCourseCategoryViewSet, basename='admin-course-category')
router.register('prices', AdminCoursePriceViewSet, basename='admin-price')
router.register('coupons', AdminCouponViewSet, basename='admin-coupon')
router.register('routines', AdminRoutineViewSet, basename='admin-routine')
router.register('course-materials', AdminCourseMaterialViewSet, basename='admin-course-material')
router.register('sections', AdminSectionViewSet, basename='admin-section')
router.register('contents', AdminContentViewSet, basename='admin-content')
router.register('courses', AdminCourseViewSet, basename='admin-course')
# The per-course assignment lives with the course it points at.
router.register('course-teachers', AdminCourseTeacherViewSet, basename='admin-course-teacher')

# Explicit routes come before the routers so a literal segment is never
# mistaken for a detail lookup.
urlpatterns = [
    path(
        'contents/<int:pk>/toggle/',
        AdminContentToggleAPIView.as_view(),
        name='admin_content_toggle',
    ),
    path(
        'courses/<int:pk>/enrollments/',
        AdminCourseEnrolledUserListAPIView.as_view(),
        name='admin_course_users',
    ),
    # One resource, a method per action: POST attaches, PATCH amends, DELETE
    # removes. Replaces the three POST-only endpoints the legacy API called
    # user-attach / user-update / user-remove.
    path('enrollments/', AdminEnrollmentAPIView.as_view(), name='admin_enrollment'),
] + router.urls
