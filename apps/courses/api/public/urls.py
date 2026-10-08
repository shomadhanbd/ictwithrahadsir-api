from django.urls import path

from apps.courses.api.public.views import (
    ContentDetailAPIView,
    CourseProgressAPIView,
    MyCourseListAPIView,
    PublicCourseDetailAPIView,
    PublicCourseListAPIView,
)

urlpatterns = [
    path('courses/', PublicCourseListAPIView.as_view(), name='course_list'),
    path('courses/<slug:slug>/', PublicCourseDetailAPIView.as_view(), name='course_detail'),
    path('courses/<slug:slug>/progress/', CourseProgressAPIView.as_view(), name='course_progress'),
    path('contents/<int:pk>/', ContentDetailAPIView.as_view(), name='content_detail'),
    path('me/courses/', MyCourseListAPIView.as_view(), name='my_course_list'),
]
