from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.courses.api.private.views import (
    AdminContentToggleAPIView,
    AdminContentViewSet,
    AdminCourseEnrolledUserListAPIView,
    AdminCourseMaterialViewSet,
    AdminCourseStudentsExportAPIView,
    AdminCourseTeacherViewSet,
    AdminCourseViewSet,
    AdminEnrollmentAPIView,
    AdminRoutineViewSet,
    AdminSectionViewSet,
)

router = SimpleRouter()
router.register('routines', AdminRoutineViewSet, basename='admin-routine')
router.register('course-materials', AdminCourseMaterialViewSet, basename='admin-course-material')
router.register('sections', AdminSectionViewSet, basename='admin-section')
router.register('contents', AdminContentViewSet, basename='admin-content')
router.register('courses', AdminCourseViewSet, basename='admin-course')
router.register('course-teachers', AdminCourseTeacherViewSet, basename='admin-course-teacher')

urlpatterns = [
    path('contents/<int:pk>/toggle/', AdminContentToggleAPIView.as_view(), name='admin_content_toggle'),
    path('courses/<int:pk>/enrollments/', AdminCourseEnrolledUserListAPIView.as_view(), name='admin_course_users'),
    path(
        'courses/<int:pk>/enrollments/export/',
        AdminCourseStudentsExportAPIView.as_view(),
        name='admin_course_users_export',
    ),
    path('enrollments/', AdminEnrollmentAPIView.as_view(), name='admin_enrollment'),
] + router.urls
