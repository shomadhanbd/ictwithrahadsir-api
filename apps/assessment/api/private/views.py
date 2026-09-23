from rest_framework.generics import ListAPIView

from apps.assessment.api.serializers import (
    AdminExamAttemptSerializer,
    QuestionBankSerializer,
    QuestionSerializer,
)
from apps.assessment.models import ExamAttempt, Question, QuestionBank
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsTeachingStaff
from apps.core.api.viewsets import AdminModelViewSet


class AdminQuestionBankViewSet(AdminModelViewSet):
    permission_classes = [IsTeachingStaff]
    queryset = QuestionBank.objects.all()
    serializer_class = QuestionBankSerializer
    # The panel ships a search box against this; without it the global
    # SearchFilter matches on nothing and quietly returns the whole folder.
    search_fields = ['title']

    def get_queryset(self):
        qs = super().get_queryset()
        mcq_store_id = self.request.query_params.get('mcq_store_id')
        if mcq_store_id:
            return qs.filter(parent_id=mcq_store_id)
        if self.action == 'list':
            # Top level only, so the admin panel can lazily expand the tree.
            return qs.filter(parent__isnull=True)
        return qs


class AdminQuestionViewSet(AdminModelViewSet):
    permission_classes = [IsTeachingStaff]
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    search_fields = ['question', 'a', 'b', 'c', 'd', 'e', 'explanation']

    def get_queryset(self):
        qs = super().get_queryset()
        mcq_store_id = self.request.query_params.get('mcq_store_id')
        if mcq_store_id:
            qs = qs.filter(bank_id=mcq_store_id)
        return qs


class AdminExamAttemptListAPIView(ListAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminExamAttemptSerializer
    pagination_class = LaravelStylePageNumberPagination

    def get_queryset(self):
        # `Meta.ordering` sorts by marks then duration, which ties whenever
        # two students score the same in the same time -- and a tie is an
        # undefined page boundary, so a row can appear twice or not at all
        # while paging. `-id` breaks the tie without changing the ranking.
        qs = ExamAttempt.objects.select_related('user', 'user__student', 'exam__content').order_by(
            '-marks', 'duration', '-id'
        )
        exam_id = self.request.query_params.get('exam_id')
        if exam_id:
            # Exam.pk is the Content pk, so the admin panel's existing
            # ?exam_id= values keep matching.
            qs = qs.filter(exam_id=exam_id)
        return qs
