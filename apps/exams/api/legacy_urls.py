"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.exams.api.v1.views import (
    AdminExamResultListAPIView,
    AdminMcqQuestionViewSet,
    AdminMcqStoreViewSet,
    ExamAPIView,
    ExamRankingAPIView,
)


router = SimpleRouter(trailing_slash=False)
router.register('admin/mcq-store', AdminMcqStoreViewSet, basename='admin-mcq-store')
router.register('admin/mcq', AdminMcqQuestionViewSet, basename='admin-mcq')

urlpatterns = [
    path('exams/<int:pk>', ExamAPIView.as_view()),
    path('ranking/<int:pk>', ExamRankingAPIView.as_view()),
    path('admin/result', AdminExamResultListAPIView.as_view()),
] + router.urls
