from django.urls import path

from apps.exam.api.private.views import (
    AdminExamAttemptDetailAPIView,
    AdminExamAttemptExportAPIView,
    AdminExamAttemptListAPIView,
    AdminExamDetailAPIView,
    AdminExamListCreateAPIView,
    AdminExamRegradeAPIView,
    AdminExamSectionDetailAPIView,
    AdminExamSectionListCreateAPIView,
    AdminExamSectionQuestionBulkAPIView,
)

urlpatterns = [
    path('exams/', AdminExamListCreateAPIView.as_view(), name='admin_exam_list'),
    path('exams/<int:pk>/', AdminExamDetailAPIView.as_view(), name='admin_exam_detail'),
    path('exams/<int:pk>/attempts/', AdminExamAttemptListAPIView.as_view(), name='admin_exam_attempts'),
    path('exams/<int:pk>/attempts/export/', AdminExamAttemptExportAPIView.as_view(), name='admin_exam_attempts_export'),
    path(
        'exams/<int:pk>/attempts/<int:attempt_id>/',
        AdminExamAttemptDetailAPIView.as_view(),
        name='admin_exam_attempt_detail',
    ),
    path('exams/<int:pk>/regrade/', AdminExamRegradeAPIView.as_view(), name='admin_exam_regrade'),
    path('exam-sections/', AdminExamSectionListCreateAPIView.as_view(), name='admin_exam_section_list'),
    path('exam-sections/<int:pk>/', AdminExamSectionDetailAPIView.as_view(), name='admin_exam_section_detail'),
    path(
        'exam-sections/<int:pk>/questions/',
        AdminExamSectionQuestionBulkAPIView.as_view(),
        name='admin_exam_section_question_bulk',
    ),
]
