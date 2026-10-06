from django.urls import path

from apps.academic.api.public.views import (
    PublicBatchListAPIView,
    PublicClassLevelListAPIView,
    PublicGroupListAPIView,
)

urlpatterns = [
    path('class-levels/', PublicClassLevelListAPIView.as_view(), name='class_level_list'),
    path('groups/', PublicGroupListAPIView.as_view(), name='group_list'),
    path('batches/', PublicBatchListAPIView.as_view(), name='batch_list'),
]
