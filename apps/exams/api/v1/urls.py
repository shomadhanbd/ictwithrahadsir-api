from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.exams.api.v1.views import (
    AdminExamResultListAPIView,
    AdminMcqQuestionViewSet,
    AdminMcqStoreViewSet,
    ExamAPIView,
    ExamRankingAPIView,
)

app_name = 'v1'

router = SimpleRouter(trailing_slash=False)
router.register('admin/mcq-store', AdminMcqStoreViewSet, basename='admin-mcq-store')
router.register('admin/mcq', AdminMcqQuestionViewSet, basename='admin-mcq')

urlpatterns = [
    path('exams/<int:pk>', ExamAPIView.as_view(), name='exam_detail'),
    path('ranking/<int:pk>', ExamRankingAPIView.as_view(), name='exam_ranking'),
    path('admin/result', AdminExamResultListAPIView.as_view(), name='admin_exam_results'),
] + router.urls
