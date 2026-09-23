from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.assessment.api.private.views import (
    AdminExamAttemptListAPIView,
    AdminQuestionBankViewSet,
    AdminQuestionViewSet,
)

#: No `app_name` -- see the note in the sibling `public/urls.py`.
router = SimpleRouter()
# `mcq-store` said nothing about what it holds; these are folders of
# questions, and `mcq` alone was the question itself.
router.register('mcq-folders', AdminQuestionBankViewSet, basename='admin-mcq-store')
router.register('mcq-questions', AdminQuestionViewSet, basename='admin-mcq')

urlpatterns = [
    path('exam-results/', AdminExamAttemptListAPIView.as_view(), name='admin_exam_results'),
] + router.urls
