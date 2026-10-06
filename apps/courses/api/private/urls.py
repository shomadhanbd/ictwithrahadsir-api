from django.urls import path

from apps.courses.api.private.views import (
    AdminContentDetailAPIView,
    AdminContentListCreateAPIView,
    AdminContentToggleAPIView,
    AdminCourseDetailAPIView,
    AdminCourseEnrolledUserListAPIView,
    AdminCourseListCreateAPIView,
    AdminCourseMaterialDetailAPIView,
    AdminCourseMaterialListCreateAPIView,
    AdminCourseStudentsExportAPIView,
    AdminCourseTeacherDetailAPIView,
    AdminCourseTeacherListCreateAPIView,
    AdminEnrollmentAPIView,
    AdminRoutineDetailAPIView,
    AdminRoutineListCreateAPIView,
    AdminSectionDetailAPIView,
    AdminSectionListCreateAPIView,
    AdminSectionMoveAPIView,
)

urlpatterns = [
    path('courses/', AdminCourseListCreateAPIView.as_view(), name='admin_course_list'),
    path('courses/<int:pk>/', AdminCourseDetailAPIView.as_view(), name='admin_course_detail'),
    path('courses/<int:pk>/enrollments/', AdminCourseEnrolledUserListAPIView.as_view(), name='admin_course_users'),
    path(
        'courses/<int:pk>/enrollments/export/',
        AdminCourseStudentsExportAPIView.as_view(),
        name='admin_course_users_export',
    ),
    path('sections/', AdminSectionListCreateAPIView.as_view(), name='admin_section_list'),
    path('sections/<int:pk>/', AdminSectionDetailAPIView.as_view(), name='admin_section_detail'),
    path('sections/<int:pk>/move/', AdminSectionMoveAPIView.as_view(), name='admin_section_move'),
    path('contents/', AdminContentListCreateAPIView.as_view(), name='admin_content_list'),
    path('contents/<slug:slug>/', AdminContentDetailAPIView.as_view(), name='admin_content_detail'),
    path('contents/<int:pk>/toggle/', AdminContentToggleAPIView.as_view(), name='admin_content_toggle'),
    path('routines/', AdminRoutineListCreateAPIView.as_view(), name='admin_routine_list'),
    path('routines/<int:pk>/', AdminRoutineDetailAPIView.as_view(), name='admin_routine_detail'),
    path('course-materials/', AdminCourseMaterialListCreateAPIView.as_view(), name='admin_course_material_list'),
    path(
        'course-materials/<int:pk>/',
        AdminCourseMaterialDetailAPIView.as_view(),
        name='admin_course_material_detail',
    ),
    path('course-teachers/', AdminCourseTeacherListCreateAPIView.as_view(), name='admin_course_teacher_list'),
    path('course-teachers/<int:pk>/', AdminCourseTeacherDetailAPIView.as_view(), name='admin_course_teacher_detail'),
    path('enrollments/', AdminEnrollmentAPIView.as_view(), name='admin_enrollment'),
]
