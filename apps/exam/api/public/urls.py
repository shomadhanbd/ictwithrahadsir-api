from django.urls import path

from apps.exam.api.public.views import (
    AttemptAnswersAPIView,
    AttemptDetailAPIView,
    AttemptResultAPIView,
    AttemptSheetFilesAPIView,
    AttemptSubmitAPIView,
    ExamDetailAPIView,
    ExamRankingAPIView,
    ExamStartAPIView,
    MyExamListAPIView,
)

urlpatterns = [
    path('me/exams/', MyExamListAPIView.as_view(), name='my_exams'),
    path('exams/<int:pk>/', ExamDetailAPIView.as_view(), name='exam_detail'),
    path('exams/<int:pk>/attempts/', ExamStartAPIView.as_view(), name='exam_start'),
    path('exams/<int:pk>/ranking/', ExamRankingAPIView.as_view(), name='exam_ranking'),
    path('exam-attempts/<int:pk>/', AttemptDetailAPIView.as_view(), name='attempt_detail'),
    path('exam-attempts/<int:pk>/answers/', AttemptAnswersAPIView.as_view(), name='attempt_answers'),
    path('exam-attempts/<int:pk>/submit/', AttemptSubmitAPIView.as_view(), name='attempt_submit'),
    path('exam-attempts/<int:pk>/result/', AttemptResultAPIView.as_view(), name='attempt_result'),
    path(
        'exam-attempts/<int:pk>/sheets/<int:section_question_id>/files/',
        AttemptSheetFilesAPIView.as_view(),
        name='attempt_sheet_files',
    ),
]
