from django.urls import path

from apps.question.api.private.views import (
    AdminQuestionBlockDetailAPIView,
    AdminQuestionBlockListCreateAPIView,
    AdminQuestionBlockSaveAPIView,
    AdminQuestionSourceDetailAPIView,
    AdminQuestionSourceListCreateAPIView,
    AdminQuestionTypeListAPIView,
    AdminRefreshQuestionCountsAPIView,
)

urlpatterns = [
    path('question-blocks/', AdminQuestionBlockListCreateAPIView.as_view(), name='admin_question_block_list'),
    path('question-blocks/<int:pk>/', AdminQuestionBlockDetailAPIView.as_view(), name='admin_question_block_detail'),
    path('question-blocks/save/', AdminQuestionBlockSaveAPIView.as_view(), name='admin_question_block_save'),
    path('question-sources/', AdminQuestionSourceListCreateAPIView.as_view(), name='admin_question_source_list'),
    path('question-sources/<int:pk>/', AdminQuestionSourceDetailAPIView.as_view(), name='admin_question_source_detail'),
    path('question-types/', AdminQuestionTypeListAPIView.as_view(), name='admin_question_type_list'),
    path('question-counts/refresh/', AdminRefreshQuestionCountsAPIView.as_view(), name='admin_question_counts_refresh'),
]
