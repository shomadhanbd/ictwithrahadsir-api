from django.urls import path

from apps.profiles.api.private.views import (
    AdminTeacherDetailAPIView,
    AdminTeacherListCreateAPIView,
    AdminTeacherLookupAPIView,
)

urlpatterns = [
    path('teachers/', AdminTeacherListCreateAPIView.as_view(), name='admin_teacher_list'),
    path('teachers/lookup/', AdminTeacherLookupAPIView.as_view(), name='admin_teacher_lookup'),
    path('teachers/<int:pk>/', AdminTeacherDetailAPIView.as_view(), name='admin_teacher_detail'),
]
