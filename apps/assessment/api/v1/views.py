from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.core.api.viewsets import AdminModelViewSet
from apps.courses.models import Content
from apps.assessment.api.v1.serializers import (
    AdminExamAttemptSerializer,
    ExamMcqSerializer,
    QuestionSerializer,
    QuestionBankSerializer,
    RankEntrySerializer,
)
from apps.assessment.models import Exam, ExamAttempt, Question, QuestionBank


def result_payload(result):
    if not result:
        return None
    return {
        'marks': result.marks,
        'positive_marks': result.positive_marks,
        'negative_marks': result.negative_marks,
        'duration': result.duration,
        'submitted': result.submitted,
        'answers': result.answers,
    }


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

        # The answer key is part of the review paper, not the exam paper: it
        # goes out only once this user has an attempt on record, and not
        # before the configured publish time. The client re-fetches after
        # submitting to pick it up.
        published = exam.results_published
        question_context = {'reveal_answers': result is not None and published}

        return Response(
            {
                'id': content.id,
                'title': content.title,
                'duration': exam.duration_minutes,
                'total_marks': exam.total_marks,
                'pass_marks': exam.pass_marks,
                'positive_marks': exam.positive_marks,
                'negative_marks': exam.negative_marks,
                'start_time': exam.start_time,
                'end_time': exam.end_time,
                'result_publish_time': exam.result_publish_time,
                # Additive: lets the client say "results not published yet"
                # instead of silently showing an unmarked review paper.
                'result_published': published,
                'question': {
                    'id': content.id,
                    'exam_id': content.id,
                    'body': {
                        'sections': [
                            {
                                'title': (
                                    exam.question_bank.title
                                    if exam.question_bank
                                    else content.title
                                ),
                                'required': True,
                                'questions': ExamMcqSerializer(
                                    questions, many=True, context=question_context
                                ).data,
                            }
                        ],
                        'max_sections': 1,
                    },
                },
                'result': result_payload(result),
            }
        )

class ExamSubmissionAPIView(BaseExamAPIView):
    """POST /exams/<id>/submission/ -- sit the exam once and get the marks."""

    def post(self, request, pk):
        exam = self.get_exam(pk)
        content = exam.content
        if not content.is_accessible_by(request.user):
            raise PermissionDenied('Not subscribed')
        if ExamAttempt.objects.filter(exam=exam, user=request.user).exists():
            raise ValidationError({'exam': ['You have already submitted this exam.']})

        sections = request.data.get('sections', [])
        if not isinstance(sections, list):
            raise ValidationError({'sections': ['Must be a list.']})

        positive = exam.positive_marks or Decimal('1')
        negative = exam.negative_marks or Decimal('0')
        marks = self._score(sections, positive, negative)

        result = ExamAttempt.objects.create(
            exam=exam,
            user=request.user,
            marks=marks,
            positive_marks=positive,
            negative_marks=negative,
            duration=int(request.data.get('duration') or 0),
            submitted=True,
            answers=sections,
        )
        return Response(result_payload(result), status=status.HTTP_201_CREATED)

    def _score(self, sections, positive, negative):
        """Mark the paper.

        The answer keys are fetched in one query rather than one per
        question: a 100-question paper used to issue 100 SELECTs on submit,
        at the exact moment a whole class hits the endpoint together.
        """
        def question_id(answer):
            """The referenced question id, or None if it isn't one.

            The client sends whatever it likes here; a non-numeric id used to
            reach the ORM and raise ValueError, i.e. a 500 that lost the whole
            submission. It is now simply an answer that matches no question.
            """
            try:
                return int(answer.get('mcq_id'))
            except (TypeError, ValueError):
                return None

        submitted = [
            (question_id(answer), (answer.get('user_answer') or '').strip().lower())
            for section in sections
            if isinstance(section, dict)
            for answer in section.get('answers', [])
            if isinstance(answer, dict)
        ]
        keys = dict(
            Question.objects.filter(
                pk__in={qid for qid, _ in submitted if qid is not None}
            ).values_list('id', 'answer')
        )

        total = Decimal('0')
        for qid, user_answer in submitted:
            correct = keys.get(qid)
            if correct is None or not user_answer:
                continue
            total += positive if user_answer == correct else -negative
        return total


class ExamAPIView(ExamDetailAPIView, ExamSubmissionAPIView):
    """The legacy flat API served both the paper and its submission from one
    path. Kept so `/api/exams/<id>` keeps accepting GET and POST."""


class ExamRankingAPIView(BaseExamAPIView):
    """Leaderboard for one exam, plus the caller's own position."""

    RANKING_LIMIT = 100

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
            {
                'exam_title': exam.content.title,
                'user_rank': user_rank if published else None,
                'user_result': RankEntrySerializer(user_result).data if user_result else None,
                'rankings': (
                    RankEntrySerializer(results[: self.RANKING_LIMIT], many=True).data
                    if published
                    else []
                ),
                'result_published': published,
                'result_publish_time': exam.result_publish_time,
            }
        )


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminQuestionBankViewSet(AdminModelViewSet):
    queryset = QuestionBank.objects.all()
    serializer_class = QuestionBankSerializer

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
        qs = ExamAttempt.objects.select_related('user', 'exam__content')
        exam_id = self.request.query_params.get('exam_id')
        if exam_id:
            # Exam.pk is the Content pk, so the admin panel's existing
            # ?exam_id= values keep matching.
            qs = qs.filter(exam_id=exam_id)
        return qs
