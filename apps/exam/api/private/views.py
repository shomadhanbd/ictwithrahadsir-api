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
    WrittenMarksSerializer,
    attempt_review_payload,
    attempt_rows,
    exam_attempts_header,
)
from apps.exam.exports import RESULT_COLUMNS, result_rows
from apps.exam.models import Exam
from apps.exam.services import exams as exam_service
from apps.exam.services import grading
from apps.exam.services import sections as section_service
from apps.exam.services.attempts import settled


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
    # A class attribute, not get_queryset(): ExamScopedAdminMixin narrows it to the teacher's own exams.
    queryset = selectors.admin_exam_sections()

    search_fields = ["title"]
    filterset_fields = ["exam", "question_type", "subject"]
    exam_path = "exam"


class AdminExamSectionDetailAPIView(ExamScopedAdminMixin, RetrieveUpdateDestroyAPIView):
    serializer_class = AdminExamSectionSerializer
    queryset = selectors.admin_exam_sections()

    exam_path = "exam"

    def perform_destroy(self, instance):
        section_service.delete_section(instance)


class AdminExamSectionQuestionBulkAPIView(APIView):
    """The picker's endpoint: a whole section's questions in one call."""

    permission_classes = [IsExamAuthor]
    serializer_class = ExamSectionQuestionBulkSerializer

    def get_section(self, request, pk, *, writing=False):
        section = selectors.exam_section(pk)
        selectors.assert_may_author_exam(request.user, section.exam)
        if writing:
            validators.validate_paper_is_editable(section.exam)
        return section

    def put(self, request, pk):
        """Replaces the section's questions with `block_ids`, in that order."""
        section = self.get_section(request, pk, writing=True)
        body = ExamSectionQuestionBulkSerializer(data=request.data, context={"section": section})
        body.is_valid(raise_exception=True)
        section_service.set_section_blocks(section, body.validated_data["block_ids"], replace=True)
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
        if request.query_params.get("to_mark") in ("1", "true"):
            attempts = attempts.filter(awaiting_marking=True)
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


class AdminExamAttemptMarksAPIView(ExamScopedAdminMixin, GenericAPIView):
    """A teacher's marks for the written (CQ) parts of one submitted attempt: PUT `{marks: [{question_id, marks}]}`."""

    queryset = Exam.objects.all()

    def put(self, request, pk, attempt_id):
        exam = self.get_exam()
        attempt = settled(exam.attempts.filter(pk=attempt_id)).select_related("user").get()
        body = WrittenMarksSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        attempt = grading.mark_written(attempt, body.validated_data["marks"], by=request.user)
        return Response(attempt_review_payload(exam, attempt))


class AdminExamRegradeAPIView(ExamScopedAdminMixin, GenericAPIView):
    """Re-marks every submitted attempt against the current answer key."""

    queryset = Exam.objects.all()

    def post(self, request, pk):
        return Response({"regraded": grading.regrade(self.get_exam())})
