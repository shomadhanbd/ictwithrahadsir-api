from django.urls import include, path

from apps.academic.api.v1.views import (
    AdminBatchDetailAPIView,
    AdminBatchListCreateAPIView,
    AdminClassLevelDetailAPIView,
    AdminClassLevelListCreateAPIView,
    AdminGroupDetailAPIView,
    AdminGroupListCreateAPIView,
    AdminSubjectDetailAPIView,
    AdminSubjectListCreateAPIView,
)

app_name = 'v1'

admin_patterns = [
    path('class-levels/', AdminClassLevelListCreateAPIView.as_view(), name='admin_class_level_list'),
    path(
        'class-levels/<int:pk>/',
        AdminClassLevelDetailAPIView.as_view(),
        name='admin_class_level_detail',
    ),
    path('groups/', AdminGroupListCreateAPIView.as_view(), name='admin_group_list'),
    path('groups/<int:pk>/', AdminGroupDetailAPIView.as_view(), name='admin_group_detail'),
    path('subjects/', AdminSubjectListCreateAPIView.as_view(), name='admin_subject_list'),
    path('subjects/<int:pk>/', AdminSubjectDetailAPIView.as_view(), name='admin_subject_detail'),
    path('batches/', AdminBatchListCreateAPIView.as_view(), name='admin_batch_list'),
    path('batches/<int:pk>/', AdminBatchDetailAPIView.as_view(), name='admin_batch_detail'),
]

urlpatterns = [
    path('admin/', include(admin_patterns)),
]
