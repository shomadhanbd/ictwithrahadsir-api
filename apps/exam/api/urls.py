from django.urls import include, path

from apps.exam.api.private.views import (
    AdminExamDetailAPIView,
    AdminExamListCreateAPIView,
    AdminExamSectionDetailAPIView,
    AdminExamSectionListCreateAPIView,
    AdminExamSectionQuestionBulkAPIView,
    AdminExamSectionQuestionDetailAPIView,
    AdminExamSectionQuestionListCreateAPIView,
)

app_name = 'exam'

admin_patterns = [
    path('exams/', AdminExamListCreateAPIView.as_view(), name='admin_exam_list'),
    path('exams/<int:pk>/', AdminExamDetailAPIView.as_view(), name='admin_exam_detail'),
    path('exam-sections/', AdminExamSectionListCreateAPIView.as_view(), name='admin_exam_section_list'),
    path(
        'exam-sections/<int:pk>/',
        AdminExamSectionDetailAPIView.as_view(),
        name='admin_exam_section_detail',
    ),
    path(
        'exam-sections/<int:pk>/questions/',
        AdminExamSectionQuestionBulkAPIView.as_view(),
        name='admin_exam_section_question_bulk',
    ),
    path(
        'exam-section-questions/',
        AdminExamSectionQuestionListCreateAPIView.as_view(),
        name='admin_exam_section_question_list',
    ),
    path(
        'exam-section-questions/<int:pk>/',
        AdminExamSectionQuestionDetailAPIView.as_view(),
        name='admin_exam_section_question_detail',
    ),
]

urlpatterns = [
    path('private/', include(admin_patterns)),
]
