from django.urls import path

from apps.courses.api.public.views import (
    ContentDetailAPIView,
    ContentPdfAPIView,
    CourseMaterialListAPIView,
    CourseProgressAPIView,
    MyCourseListAPIView,
    PublicCourseCategoryListAPIView,
    PublicCourseDetailAPIView,
    PublicCourseListAPIView,
)

#: No `app_name`: assembled into the app's single namespace by
#: `apps.courses.api.urls`, so route names survive the split.
urlpatterns = [
    path('courses/', PublicCourseListAPIView.as_view(), name='course_list'),
    path('courses/<slug:slug>/', PublicCourseDetailAPIView.as_view(), name='course_detail'),
    path('course-categories/', PublicCourseCategoryListAPIView.as_view(), name='course_category_list'),
    path(
        'courses/<slug:slug>/progress/',
        CourseProgressAPIView.as_view(),
        name='course_progress',
    ),
    path(
        'courses/<slug:slug>/materials/',
        CourseMaterialListAPIView.as_view(),
        name='course_material_list',
    ),
    path('contents/<slug:slug>/', ContentDetailAPIView.as_view(), name='content_detail'),
    path('contents/<slug:slug>/pdf/', ContentPdfAPIView.as_view(), name='content_pdf'),
    # Scoped to the caller, so it hangs off /me/ like the profile does.
    path('me/courses/', MyCourseListAPIView.as_view(), name='my_course_list'),
]
