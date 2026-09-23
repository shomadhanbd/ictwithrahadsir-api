from django.urls import path

from apps.assessment.api.public.views import (
    ExamDetailAPIView,
    ExamRankingAPIView,
    ExamSubmissionAPIView,
    PracticeBankListAPIView,
    PracticeQuestionListAPIView,
)

#: No `app_name`: assembled into the app's single namespace by
#: `apps.assessment.api.urls`, so route names survive the split.
urlpatterns = [
    # Free practice — the MCQ bank's only route that does not require an
    # enrolment and a scheduled exam.
    path('practice/topics/', PracticeBankListAPIView.as_view(), name='practice_topics'),
    path('practice/questions/', PracticeQuestionListAPIView.as_view(), name='practice_questions'),
    path('exams/<int:pk>/', ExamDetailAPIView.as_view(), name='exam_detail'),
    # Sitting the exam creates a submission, so it is its own resource rather
    # than a POST to the paper.
    path('exams/<int:pk>/submission/', ExamSubmissionAPIView.as_view(), name='exam_submission'),
    # The ranking belongs to the exam; `ranking/<id>` hid that the id was a
    # content id at all.
    path('exams/<int:pk>/ranking/', ExamRankingAPIView.as_view(), name='exam_ranking'),
]
