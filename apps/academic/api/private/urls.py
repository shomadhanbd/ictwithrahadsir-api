from django.urls import path

from apps.academic.api.private.views import (
    AdminBatchDetailAPIView,
    AdminBatchListCreateAPIView,
    AdminChapterDetailAPIView,
    AdminChapterListCreateAPIView,
    AdminClassLevelDetailAPIView,
    AdminClassLevelListCreateAPIView,
    AdminGroupListAPIView,
    AdminSubjectDetailAPIView,
    AdminSubjectListCreateAPIView,
    AdminTopicDetailAPIView,
    AdminTopicListCreateAPIView,
)

urlpatterns = [
    path('class-levels/', AdminClassLevelListCreateAPIView.as_view(), name='admin_class_level_list'),
    path('class-levels/<int:pk>/', AdminClassLevelDetailAPIView.as_view(), name='admin_class_level_detail'),
    path('groups/', AdminGroupListAPIView.as_view(), name='admin_group_list'),
    path('subjects/', AdminSubjectListCreateAPIView.as_view(), name='admin_subject_list'),
    path('subjects/<int:pk>/', AdminSubjectDetailAPIView.as_view(), name='admin_subject_detail'),
    path('chapters/', AdminChapterListCreateAPIView.as_view(), name='admin_chapter_list'),
    path('chapters/<int:pk>/', AdminChapterDetailAPIView.as_view(), name='admin_chapter_detail'),
    path('topics/', AdminTopicListCreateAPIView.as_view(), name='admin_topic_list'),
    path('topics/<int:pk>/', AdminTopicDetailAPIView.as_view(), name='admin_topic_detail'),
    path('batches/', AdminBatchListCreateAPIView.as_view(), name='admin_batch_list'),
    path('batches/<int:pk>/', AdminBatchDetailAPIView.as_view(), name='admin_batch_detail'),
]
