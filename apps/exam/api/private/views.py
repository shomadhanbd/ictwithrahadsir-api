from rest_framework.generics import GenericAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.views.exports import csv_response
from apps.exam import selectors, validators
from apps.exam.api.private.filters import ExamFilter
from apps.exam.api.private.permissions import IsExamAuthor
from apps.exam.api.private.serializers import (
    AdminExamDetailSerializer,
    AdminExamSectionSerializer,
    AdminExamSerializer,
    ExamSectionQuestionBulkSerializer,
    attempt_review_payload,
    attempt_rows,
    exam_attempts_header,
)
from apps.exam.exports import RESULT_COLUMNS, result_rows
from apps.exam.models import Exam, ExamSection
from apps.exam.services import exams as exam_service
from apps.exam.services import grading
from apps.exam.services import sections as section_service
from apps.exam.services.attempts import settled
from apps.question.api.private.serializers import AdminQuestionBlockSerializer
from apps.question.selectors import admin_blocks


class ExamScopedAdminMixin:
    """Restricts an exam-shaped endpoint to the exams the caller may author; `exam_path` leads to the exam."""

    permission_classes = [IsExamAuthor]
    exam_path = ""

    def exam_for(self, obj):
        for name in filter(None, self.exam_path.split("__")):
            obj = getattr(obj, name)
        return obj

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        return selectors.authored_by(queryset, user, exam_path=self.exam_path)

    def get_exam(self):
        """The URL's exam, through the same scoping as the list."""
        return self.get_queryset().select_related("lesson__course").get(pk=self.kwargs["pk"])


class AdminExamListCreateAPIView(ExamScopedAdminMixin, ListCreateAPIView):
    """POST always fails validation: exams are created as lessons inside a course."""

    serializer_class = AdminExamSerializer
    queryset = selectors.admin_exams()
    search_fields = ["title", "description"]
    filterset_class = ExamFilter


class AdminExamDetailAPIView(ExamScopedAdminMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = AdminExamDetailSerializer
    queryset = selectors.admin_exams(full_sections=True)

    def perform_destroy(self, instance):
        exam_service.delete_exam(instance)


class AdminExamSectionListCreateAPIView(ExamScopedAdminMixin, ListCreateAPIView):
    serializer_class = AdminExamSectionSerializer
    queryset = ExamSection.objects.select_related("exam", "subject")
    search_fields = ["title"]
    filterset_fields = ["exam", "question_type", "subject"]
    exam_path = "exam"


class AdminExamSectionDetailAPIView(ExamScopedAdminMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = AdminExamSectionSerializer
    queryset = ExamSection.objects.select_related("exam", "subject")
    exam_path = "exam"

    def perform_destroy(self, instance):
        section_service.delete_section(instance)


class AdminExamSectionQuestionBulkAPIView(APIView):
    """The picker's endpoint: a whole section's questions in one call."""

    permission_classes = [IsExamAuthor]
    serializer_class = ExamSectionQuestionBulkSerializer

    def get_section(self, request, pk, *, writing=False):
        section = ExamSection.objects.select_related("exam").get(pk=pk)
        selectors.assert_may_author_exam(request.user, section.exam)
        if writing:
            validators.validate_paper_is_editable(section.exam)
        return section

    def _blocks(self, request, section, *, check_blocks=True):
        body = ExamSectionQuestionBulkSerializer(
            data=request.data, context={"section": section, "check_blocks": check_blocks}
        )
        body.is_valid(raise_exception=True)
        return body.validated_data

    def get(self, request, pk):
        section = self.get_section(request, pk)
        blocks = {block.pk: block for block in admin_blocks().filter(exam_usages__section=section)}
        rows = [
            {
                "id": pick.pk,
                "marks": str(pick.marks),
                "order": pick.order,
                "block": AdminQuestionBlockSerializer(blocks[pick.block_id]).data if pick.block_id in blocks else None,
            }
            for pick in section.section_questions.order_by("order", "id")
        ]
        return Response({"data": rows})

    def post(self, request, pk):
        section = self.get_section(request, pk, writing=True)
        data = self._blocks(request, section)
        section_service.set_section_blocks(section, data["block_ids"], replace=data["mode"] == "replace")
        return self._section_response(request, section)

    def put(self, request, pk):
        section = self.get_section(request, pk, writing=True)
        section_service.set_section_blocks(section, self._blocks(request, section)["block_ids"], replace=True)
        return self._section_response(request, section)

    def delete(self, request, pk):
        section = self.get_section(request, pk, writing=True)
        section_service.remove_section_blocks(section, self._blocks(request, section, check_blocks=False)["block_ids"])
        return self._section_response(request, section)

    def _section_response(self, request, section):
        section.refresh_from_db()
        return Response(AdminExamSectionSerializer(section, context={"request": request}).data)


class AdminExamAttemptListAPIView(ExamScopedAdminMixin, GenericAPIView):
    """Every attempt at one exam, a page at a time: official ones ranked by result, practice ones after them.

    `{exam, summary}` above the usual `{data, links, meta}` page; ranks count everyone, not just the page.
    """

    queryset = Exam.objects.all()

    def get(self, request, pk):
        exam = self.get_exam()
        settled(exam.attempts.all())
        attempts = selectors.exam_submissions(
            exam,
            search=request.query_params.get("search"),
            official_only=request.query_params.get("official") in ("1", "true"),
        )
        page = self.paginate_queryset(attempts)
        response = self.get_paginated_response(attempt_rows(page, ranks=selectors.official_ranks(exam)))
        response.data = {**exam_attempts_header(exam, stats=selectors.exam_result_stats(exam)), **response.data}
        return response


class AdminExamAttemptExportAPIView(ExamScopedAdminMixin, GenericAPIView):
    """Every attempt at one exam as a CSV download, in the submissions table's order."""

    queryset = Exam.objects.all()

    def get(self, request, pk):
        exam = self.get_exam()
        settled(exam.attempts.all())
        rows = result_rows(exam, exam.attempts.results_table(), ranks=selectors.official_ranks(exam))
        return csv_response(f"exam-{exam.pk}-results.csv", RESULT_COLUMNS, rows)


class AdminExamAttemptDetailAPIView(ExamScopedAdminMixin, GenericAPIView):
    """One student's attempt, answer by answer."""

    queryset = Exam.objects.all()

    def get(self, request, pk, attempt_id):
        exam = self.get_exam()
        attempt = settled(exam.attempts.filter(pk=attempt_id)).select_related("user").get()
        return Response(attempt_review_payload(exam, attempt))


class AdminExamRegradeAPIView(ExamScopedAdminMixin, GenericAPIView):
    """Re-marks every submitted attempt against the current answer key."""

    queryset = Exam.objects.all()

    def post(self, request, pk):
        return Response({"regraded": grading.regrade(self.get_exam())})
