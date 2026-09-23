"""Admin CRUD for exam authoring.

Every class declares `permission_classes`: the project default is
`IsAuthenticatedOrReadOnly`, so one that leaves it off is world-readable.

Ownership needs **two** halves applied together -- `ExamScopedAdminMixin`
narrows the list so a teacher does not see another teacher's papers, and
`IsExamAuthor.has_object_permission` stops them opening one by id. Either alone
leaves a hole the other covers.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, Sum

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import is_full_admin
from apps.exam import services
from apps.exam.api.private.filters import ExamFilter
from apps.exam.api.private.permissions import IsExamAuthor, assert_may_author_exam
from apps.exam.api.private.serializers import (
    AdminExamDetailSerializer,
    AdminExamSectionQuestionSerializer,
    AdminExamSectionSerializer,
    AdminExamSerializer,
    ExamSectionQuestionBulkSerializer,
)
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.question.api.private.serializers import AdminQuestionBlockSerializer
from apps.question.api.private.views import block_queryset


def section_queryset():
    """Sections with their picks in order.

    The ordered `Prefetch` is not decoration: without it the picks come back in
    whatever order the database chose, so a paper's questions arrive shuffled.
    """
    picks = ExamSectionQuestion.objects.order_by("order", "id")
    return ExamSection.objects.select_related("subject").prefetch_related(Prefetch("section_questions", queryset=picks))


#: Enough of a section to say what a paper contains, and no more. `only()`
#: still has to carry the ordering columns or Django re-queries for them.
LIGHT_SECTIONS = Prefetch("sections", queryset=ExamSection.objects.only("exam_id", "question_type", "order"))


def exam_queryset(sections=LIGHT_SECTIONS):
    """A page of exams with their totals, in a fixed number of queries.

    The three aggregates all travel through the single `sections` join, so they
    do not fan out. Adding a second to-many annotation here would cross-product
    them -- put it in its own subquery instead.

    `sections` is a parameter because a lookup can only be prefetched once:
    the list wants the light version above, the detail wants the whole tree,
    and calling `prefetch_related("sections")` twice raises rather than
    overriding.
    """
    return (
        Exam.objects.select_related("created_by", "batch")
        .prefetch_related(sections)
        .annotate(
            section_count=Count("sections", distinct=True),
            selected_question_count=Sum("sections__question_count"),
            computed_marks=Sum("sections__computed_marks"),
        )
        # Spelled out, though it only repeats `Meta.ordering`. The aggregates
        # above put a GROUP BY on the query, and Django drops a model's default
        # ordering from the SQL when it does -- so the list came back in
        # whatever order the database chose, and a paginated row could show up
        # on two pages or on none.
        .order_by("-created_at", "id")
    )


def assert_paper_is_editable(exam):
    """`services.validate_paper_is_editable`, raised the way a view can.

    A serializer's `validate()` sits inside DRF's `run_validation`, which
    converts a Django `ValidationError` for us. A `destroy()` and a plain
    `APIView` do not, so one raised here would escape the handler as a 500
    rather than the 422 it is.
    """
    try:
        services.validate_paper_is_editable(exam)
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict)


class ExamScopedAdminMixin:
    """Restricts an admin exam-shaped endpoint to the teacher's own exams.

    Lives here rather than in `apps.core`: core is infrastructure and has no
    business importing a domain app, which is the same argument its own
    `CourseScopedAdminMixin` makes for reading `user.teaching` backwards.
    """

    permission_classes = [IsExamAuthor]

    #: ORM lookup from this model to the author. The per-object check walks the
    #: same path as attributes, so there is one declaration, not two that can
    #: disagree about which column decides who owns a row.
    author_path = "created_by"

    def author_id_for(self, obj):
        """The author's id, reached without a query off the select_related row."""
        *relations, author = self.author_path.split("__")
        for name in relations:
            obj = getattr(obj, name, None)
            if obj is None:
                return None
        return getattr(obj, f"{author}_id", None)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # drf-spectacular calls this with an anonymous user; without the guard
        # these views generate untyped and the warning baseline moves.
        if getattr(self, "swagger_fake_view", False) or not user.is_authenticated:
            return queryset.none()
        if is_full_admin(user):
            return queryset
        return queryset.filter(**{self.author_path: user})


# -- exams -------------------------------------------------------------------


class AdminExamListCreateAPIView(ExamScopedAdminMixin, ListCreateAPIView):
    serializer_class = AdminExamSerializer
    queryset = exam_queryset()
    search_fields = ["title", "slug", "description"]
    filterset_class = ExamFilter

    def perform_create(self, serializer):
        # Never from the payload: `created_by` is read-only on the serializer.
        serializer.save(created_by=self.request.user)


class AdminExamDetailAPIView(ExamScopedAdminMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = AdminExamDetailSerializer
    queryset = exam_queryset(Prefetch("sections", queryset=section_queryset()))


# -- sections ----------------------------------------------------------------


class AdminExamSectionListCreateAPIView(ExamScopedAdminMixin, ListCreateAPIView):
    serializer_class = AdminExamSectionSerializer
    queryset = ExamSection.objects.select_related("exam", "subject")
    search_fields = ["title"]
    filterset_fields = ["exam", "question_type", "subject"]
    author_path = "exam__created_by"


class AdminExamSectionDetailAPIView(ExamScopedAdminMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = AdminExamSectionSerializer
    queryset = ExamSection.objects.select_related("exam", "subject")
    author_path = "exam__created_by"

    def perform_destroy(self, instance):
        # `destroy()` runs no serializer, so the freeze is not checked for it.
        assert_paper_is_editable(instance.exam)
        instance.delete()


# -- picks -------------------------------------------------------------------


class AdminExamSectionQuestionListCreateAPIView(ExamScopedAdminMixin, ListCreateAPIView):
    serializer_class = AdminExamSectionQuestionSerializer
    queryset = ExamSectionQuestion.objects.select_related("section__exam")
    filterset_fields = ["section", "block"]
    author_path = "section__exam__created_by"


class AdminExamSectionQuestionDetailAPIView(ExamScopedAdminMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = AdminExamSectionQuestionSerializer
    queryset = ExamSectionQuestion.objects.select_related("section__exam")
    author_path = "section__exam__created_by"

    def perform_destroy(self, instance):
        assert_paper_is_editable(instance.section.exam)
        instance.delete()


class AdminExamSectionQuestionBulkAPIView(APIView):
    """The picker's endpoint: a whole section's questions in one call.

    Thirty individual POSTs would be thirty round trips, thirty permission
    checks and thirty recount queries, with no atomicity -- a failure at item
    19 leaves a half-built section to clean up by hand. One call is one
    transaction, one type-check query and one recount.

    This is a plain `APIView`, so DRF runs no object permission: it calls
    `assert_may_author_exam` itself right after fetching the section.
    """

    permission_classes = [IsExamAuthor]
    serializer_class = ExamSectionQuestionBulkSerializer

    def get_section(self, request, pk):
        """`writing=True` also refuses a published paper.

        The picker is one of the doors that used to let a live exam be gutted
        while `validate_publish` watched only the exam serializer.
        """
        section = get_object_or_404(ExamSection.objects.select_related("exam"), pk=pk)
        assert_may_author_exam(request, section.exam)
        return section

    def get_section_for_write(self, request, pk):
        section = self.get_section(request, pk)
        assert_paper_is_editable(section.exam)
        return section

    @extend_schema(
        summary="The questions in one exam section",
        responses={200: AdminQuestionBlockSerializer(many=True)},
    )
    def get(self, request, pk):
        section = self.get_section(request, pk)
        picks = section.section_questions.order_by("order", "id")
        blocks = {block.pk: block for block in block_queryset().filter(exam_usages__section=section)}

        return Response(
            {
                "data": [
                    {
                        "id": pick.pk,
                        "marks": str(pick.marks),
                        "order": pick.order,
                        "block": AdminQuestionBlockSerializer(blocks[pick.block_id]).data
                        if pick.block_id in blocks
                        else None,
                    }
                    for pick in picks
                ]
            }
        )

    @extend_schema(
        summary="Add questions to an exam section",
        request=ExamSectionQuestionBulkSerializer,
        responses={200: AdminExamSectionSerializer},
    )
    def post(self, request, pk):
        return self._write(request, pk)

    @extend_schema(
        summary="Replace an exam section's questions",
        request=ExamSectionQuestionBulkSerializer,
        responses={200: AdminExamSectionSerializer},
    )
    def put(self, request, pk):
        return self._write(request, pk, mode="replace")

    @extend_schema(
        summary="Remove questions from an exam section",
        request=ExamSectionQuestionBulkSerializer,
        responses={200: AdminExamSectionSerializer},
    )
    def delete(self, request, pk):
        section = self.get_section_for_write(request, pk)
        serializer = ExamSectionQuestionBulkSerializer(
            data=request.data, context={"section": section, "check_blocks": False}
        )
        serializer.is_valid(raise_exception=True)

        ids = [block.pk for block in serializer.validated_data["block_ids"]]
        ExamSectionQuestion.objects.filter(section=section, block_id__in=ids).delete()
        services.sync_section_totals(section)
        return self._section_response(request, section)

    def _write(self, request, pk, *, mode=None):
        """`mode` overrides the body's, so PUT always replaces."""
        section = self.get_section_for_write(request, pk)
        serializer = ExamSectionQuestionBulkSerializer(data=request.data, context={"section": section})
        serializer.is_valid(raise_exception=True)
        serializer.save(section=section, mode=mode)
        return self._section_response(request, section)

    def _section_response(self, request, section):
        """The section as it now stands -- re-read, because the counters were
        written by `sync_section_totals` and not through this instance."""
        section.refresh_from_db()
        return Response(AdminExamSectionSerializer(section, context={"request": request}).data)
