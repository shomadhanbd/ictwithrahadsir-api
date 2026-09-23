"""Admin CRUD for the question bank.

Every class declares `permission_classes`: the project default is
`IsAuthenticatedOrReadOnly`, so one that leaves it off is world-readable -- and
these payloads carry the answer key.

The tier is **teaching staff**, not full admin: a teacher cannot build an exam
out of questions they are not allowed to see. The bank is therefore shared
property -- any teacher may edit any other teacher's question, and there is no
`updated_by` to say who did. Exams are owned (`exam.Exam.created_by`);
questions are not. Answer keys stay out of *public* payloads through the
serializer split in `serializers.py`, which is unaffected by this tier.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Prefetch

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsTeachingStaff
from apps.core.api.responses import OkResponseSerializer
from apps.question import services, types
from apps.question.api.private.filters import QuestionBlockFilter
from apps.question.api.private.serializers import (
    AdminQuestionBlockSerializer,
    AdminQuestionSerializer,
    QuestionKindSerializer,
    QuestionSourceSerializer,
)
from apps.question.counts import refresh_question_counts
from apps.question.models import Question, QuestionBlock, QuestionSource


def block_queryset():
    """A page of blocks in a fixed number of queries, questions correctly ordered.

    The ordered `Prefetch` is not decoration: without it a grouped block returns
    its questions in whatever order the database chose, so a creative question's
    ক/খ/গ/ঘ arrive shuffled.
    """
    questions = Question.objects.order_by("order_in_set", "id").prefetch_related("options")
    return (
        QuestionBlock.objects.select_related("subject", "chapter")
        .prefetch_related(
            "topics",
            "sources",
            Prefetch("question_set__questions", queryset=questions),
            Prefetch("standalone_question", queryset=questions),
        )
        #: `chapter` is nullable, and where NULLs sort is backend-dependent.
        .order_by(F("chapter__chapter_number").asc(nulls_last=True), "order_in_chapter", "id")
    )


class AdminQuestionBlockListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminQuestionBlockSerializer
    queryset = block_queryset()
    #: A grouped block's questions hang off its set, so searching only the
    #: stimulus and the standalone prompt missed every question inside a group
    #: -- the majority of the bank. DRF adds the `DISTINCT` the join needs.
    search_fields = [
        "question_set__stimulus_content",
        "question_set__questions__prompt_content",
        "standalone_question__prompt_content",
        "sources__name",
    ]
    #: A FilterSet rather than `filterset_fields`: the provenance params have to
    #: share one JOIN or they match different papers. See `filters.py`.
    filterset_class = QuestionBlockFilter


class AdminQuestionBlockDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminQuestionBlockSerializer
    queryset = block_queryset()


class AdminQuestionListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminQuestionSerializer
    queryset = Question.objects.prefetch_related("options")
    search_fields = ["prompt_content", "explanation"]
    #: No `select_mode`: it moved into `metadata`, and a JSON payload is not
    #: something to filter on -- `__contains` is unsupported on SQLite.
    filterset_fields = ["question_type", "block", "question_set"]


class AdminQuestionDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminQuestionSerializer
    queryset = Question.objects.prefetch_related("options")

    def perform_destroy(self, instance):
        # `destroy()` runs no serializer, so the published-paper guard is
        # checked here -- and converted, or it would escape as a 500.
        try:
            services.validate_parts_change(
                services.owning_block(block=instance.block, question_set=instance.question_set)
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict)
        instance.delete()


class AdminQuestionSourceListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = QuestionSourceSerializer
    queryset = QuestionSource.objects.all()
    search_fields = ["name", "slug", "unit"]
    filterset_fields = ["kind", "year", "is_active"]


class AdminQuestionSourceDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = QuestionSourceSerializer
    queryset = QuestionSource.objects.all()


class AdminQuestionTypeListAPIView(APIView):
    """The question types this bank knows about, and what each can do.

    Unpaginated `{"data": [...]}`: it is a fixed handful of rows describing the
    code, not a table that grows.
    """

    permission_classes = [IsTeachingStaff]
    serializer_class = QuestionKindSerializer

    @extend_schema(summary="Question types", responses={200: QuestionKindSerializer(many=True)})
    def get(self, request):
        return Response({"data": QuestionKindSerializer(list(types.REGISTRY.values()), many=True).data})


class AdminRefreshQuestionCountsAPIView(APIView):
    """Recount the curriculum's counters (see `apps.question.counts`).

    The Question Bank's "Refresh questions" button. Counts are not kept up to
    date on each write, so this is how they catch up after questions are added.
    """

    permission_classes = [IsTeachingStaff]

    @extend_schema(summary="Refresh question counts", request=None, responses={200: OkResponseSerializer})
    def post(self, request):
        refresh_question_counts()
        return Response(OkResponseSerializer({"ok": True}).data)
