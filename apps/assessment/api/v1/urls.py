from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.assessment.api.v1.views import (
    AdminExamResultListAPIView,
    AdminMcqQuestionViewSet,
    AdminMcqStoreViewSet,
    ExamDetailAPIView,
    ExamRankingAPIView,
    ExamSubmissionAPIView,
)

app_name = 'v1'

router = SimpleRouter()
# `mcq-store` said nothing about what it holds; these are folders of
# questions, and `mcq` alone was the question itself.
router.register('admin/mcq-folders', AdminMcqStoreViewSet, basename='admin-mcq-store')
router.register('admin/mcq-questions', AdminMcqQuestionViewSet, basename='admin-mcq')

urlpatterns = [
    path('exams/<int:pk>/', ExamDetailAPIView.as_view(), name='exam_detail'),
    # Sitting the exam creates a submission, so it is its own resource rather
    # than a POST to the paper.
    path('exams/<int:pk>/submission/', ExamSubmissionAPIView.as_view(), name='exam_submission'),
    # The ranking belongs to the exam; `ranking/<id>` hid that the id was a
    # content id at all.
    path('exams/<int:pk>/ranking/', ExamRankingAPIView.as_view(), name='exam_ranking'),
    path('admin/exam-results/', AdminExamResultListAPIView.as_view(), name='admin_exam_results'),
] + router.urls
