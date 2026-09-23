from django.urls import include, path

from apps.question.api.private.views import (
    AdminQuestionBlockDetailAPIView,
    AdminQuestionBlockListCreateAPIView,
    AdminQuestionDetailAPIView,
    AdminQuestionListCreateAPIView,
    AdminQuestionSourceDetailAPIView,
    AdminQuestionSourceListCreateAPIView,
    AdminQuestionTypeListAPIView,
)

app_name = 'question'

admin_patterns = [
    path('question-blocks/', AdminQuestionBlockListCreateAPIView.as_view(), name='admin_question_block_list'),
    path(
        'question-blocks/<int:pk>/',
        AdminQuestionBlockDetailAPIView.as_view(),
        name='admin_question_block_detail',
    ),
    path('questions/', AdminQuestionListCreateAPIView.as_view(), name='admin_question_list'),
    path('questions/<int:pk>/', AdminQuestionDetailAPIView.as_view(), name='admin_question_detail'),
    path('question-sources/', AdminQuestionSourceListCreateAPIView.as_view(), name='admin_question_source_list'),
    path('question-types/', AdminQuestionTypeListAPIView.as_view(), name='admin_question_type_list'),
    path(
        'question-sources/<int:pk>/',
        AdminQuestionSourceDetailAPIView.as_view(),
        name='admin_question_source_detail',
    ),
]

urlpatterns = [
    path('private/', include(admin_patterns)),
]
