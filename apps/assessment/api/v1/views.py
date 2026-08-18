
from django.db.models import Q
from django.utils import timezone

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assessment.api.v1.serializers import (
    AdminExamAttemptSerializer,
    ExamPaperSerializer,
    ExamRankingSerializer,
    ExamResultSerializer,
    ExamSubmissionRequestSerializer,
    PracticeBankSerializer,
    PracticeQuestionSerializer,
    QuestionBankSerializer,
    QuestionSerializer,
)
from apps.assessment.models import Exam, ExamAttempt, Question, QuestionBank
from apps.assessment.selectors import practice_banks_with_counts
from apps.assessment.services import submit_exam
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet, UnpaginatedDataListMixin
from apps.courses.models import Content


class BaseExamAPIView(APIView):
    """Shared lookup for the endpoints addressed by an exam content id."""

    permission_classes = [IsAuthenticated]

    def get_exam(self, pk):
        """Resolve the Exam addressed by `pk`.

        `pk` is the Content id, which is also the Exam's primary key, so
        the public identifier is unchanged. Content that is not an exam --
        or an exam with no configuration row -- simply does not match.
        """
        exam = (
            Exam.objects.select_related('content', 'question_bank')
            .filter(pk=pk, content__type=Content.Type.EXAM, content__active=True)
            .first()
        )
        if not exam:
            raise NotFound('Exam not found.')
        return exam


class ExamDetailAPIView(BaseExamAPIView):
    """GET /exams/<id>/ -- the paper, plus this user's own attempt."""

    @extend_schema(summary='The exam paper plus the caller\'s attempt', responses={200: ExamPaperSerializer})
    def get(self, request, pk):
        exam = self.get_exam(pk)
        content = exam.content
        if not content.is_accessible_by(request.user):
            raise PermissionDenied('Not subscribed')

        now = timezone.now()
        if exam.mode == Exam.Mode.EXAM:
            if exam.start_time and now < exam.start_time:
                raise PermissionDenied('This exam has not started yet.')
            if exam.end_time and now > exam.end_time:
                raise PermissionDenied('This exam has ended.')

        questions = (
            exam.question_bank.all_questions()
            if exam.question_bank
            else Question.objects.none()
        )
        result = ExamAttempt.objects.filter(exam=exam, user=request.user).first()

        published = exam.results_published

        return Response(
            ExamPaperSerializer(
                exam,
                context={
                    'questions': questions,
                    'attempt': result,
                    # The answer key is part of the review paper, not the exam
                    # paper: it goes out only once this user has an attempt on
                    # record, and not before the configured publish time. The
                    # client re-fetches after submitting to pick it up.
                    'reveal_answers': result is not None and published,
                },
            ).data
        )


class ExamSubmissionAPIView(BaseExamAPIView):
    """POST /exams/<id>/submission/ -- sit the exam once and get the marks."""

    @extend_schema(
        summary='Hand in the paper and get the marks',
        request=ExamSubmissionRequestSerializer,
        responses={201: ExamResultSerializer},
    )
    def post(self, request, pk):
        exam = self.get_exam(pk)
        if not exam.content.is_accessible_by(request.user):
            raise PermissionDenied('Not subscribed')

        serializer = ExamSubmissionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = submit_exam(exam=exam, user=request.user, **serializer.validated_data)
        return Response(ExamResultSerializer(result).data, status=status.HTTP_201_CREATED)


class ExamRankingAPIView(BaseExamAPIView):
    """Leaderboard for one exam, plus the caller's own position."""

    RANKING_LIMIT = 100

    @extend_schema(
        summary='Leaderboard for one exam',
        responses={200: ExamRankingSerializer},
    )
    def get(self, request, pk):
        exam = self.get_exam(pk)
        results = (
            ExamAttempt.objects.filter(exam=exam)
            .select_related('user')
            .order_by('-marks', 'duration')
        )

        user_result = results.filter(user=request.user).first()
        user_rank = None
        if user_result:
            # Counted in the database. Materialising every attempt id just to
            # call .index() on it pulled the entire leaderboard into memory to
            # find one position -- on a popular exam that is every row, on
            # every load of the page.
            better = Q(marks__gt=user_result.marks) | Q(
                marks=user_result.marks, duration__lt=user_result.duration
            )
            user_rank = results.filter(better).count() + 1

        # The board is everybody else's marks, so it is the thing the publish
        # time most clearly governs. The caller's own row stays visible --
        # they already know how they did -- and the response keeps its shape
        # so the client degrades to an empty board rather than an error.
        published = exam.results_published

        return Response(
            ExamRankingSerializer(
                {
                    'exam_title': exam.content.title,
                    'user_rank': user_rank if published else None,
                    'user_result': user_result,
                    'rankings': results[: self.RANKING_LIMIT] if published else [],
                    'result_published': published,
                    'result_publish_time': exam.result_publish_time,
                }
            ).data
        )


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Free practice
# ---------------------------------------------------------------------------

PRACTICE_SAMPLE_DEFAULT = 10
PRACTICE_SAMPLE_MAX = 20


class PracticeBankListAPIView(UnpaginatedDataListMixin, ListAPIView):
    """The topics a visitor can practise, with question counts.

    The MCQ bank has only ever been reachable inside a scheduled exam, which
    means it is invisible to anyone who has not already paid — the one piece
    of content that would persuade them to.

    Only folders that actually hold questions, counted across descendants, so
    an empty or purely structural folder never offers a quiz with nothing in
    it.
    """

    permission_classes = [AllowAny]
    serializer_class = PracticeBankSerializer
    queryset = QuestionBank.objects.none()

    def get_list_payload(self, request, *args, **kwargs):
        return self.get_serializer(practice_banks_with_counts(), many=True).data


class PracticeQuestionListAPIView(UnpaginatedDataListMixin, ListAPIView):
    """A random sample of questions to practise on.

    Random and capped: the answers and explanations are included because
    nothing is scored and a practice question that cannot say why you were
    wrong is just a quiz, so the sample size is what keeps the bank from
    being lifted in one request.
    """

    permission_classes = [AllowAny]
    serializer_class = PracticeQuestionSerializer
    queryset = Question.objects.none()

    def get_list_payload(self, request, *args, **kwargs):
        questions = Question.objects.all()

        bank_id = request.query_params.get('bank_id')
        if bank_id:
            bank = QuestionBank.objects.filter(pk=bank_id).first()
            if not bank:
                raise NotFound('Topic not found.')
            questions = bank.all_questions()

        try:
            limit = int(request.query_params.get('limit', PRACTICE_SAMPLE_DEFAULT))
        except (TypeError, ValueError):
            limit = PRACTICE_SAMPLE_DEFAULT
        limit = max(1, min(limit, PRACTICE_SAMPLE_MAX))

        sample = questions.order_by('?')[:limit]
        return self.get_serializer(sample, many=True).data


class AdminQuestionBankViewSet(AdminModelViewSet):
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
    permission_classes = [IsAdminRole]
    serializer_class = AdminExamAttemptSerializer
    pagination_class = LaravelStylePageNumberPagination

    def get_queryset(self):
        # `Meta.ordering` sorts by marks then duration, which ties whenever
        # two students score the same in the same time -- and a tie is an
        # undefined page boundary, so a row can appear twice or not at all
        # while paging. `-id` breaks the tie without changing the ranking.
        qs = ExamAttempt.objects.select_related('user', 'exam__content').order_by(
            '-marks', 'duration', '-id'
        )
        exam_id = self.request.query_params.get('exam_id')
        if exam_id:
            # Exam.pk is the Content pk, so the admin panel's existing
            # ?exam_id= values keep matching.
            qs = qs.filter(exam_id=exam_id)
        return qs
