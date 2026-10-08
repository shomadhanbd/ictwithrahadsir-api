from django.core.exceptions import ValidationError
from django.utils import timezone

from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.exam import selectors
from apps.exam.api.public.serializers import (
    SaveAnswersSerializer,
    attempt_detail_payload,
    attempt_payload,
    exam_detail_payload,
    ranking_payload,
    result_payload,
    student_exams_payload,
    submitted_payload,
)
from apps.exam.services import attempts as attempt_service

RANKING_SIZE = 50


class ExamDetailAPIView(APIView):
    """The exam and the caller's attempts at it."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        exam = selectors.exam_for_student(pk, request.user)
        attempts = attempt_service.settled(selectors.attempts_of(request.user, exam))
        summary = selectors.lesson_exam_summary(exam.lesson, request.user)
        return Response(exam_detail_payload(exam, summary, attempts.order_by("number")))


class ExamStartAPIView(APIView):
    """Starts an attempt, or returns the one already open."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        attempt = attempt_service.start_attempt(selectors.exam_for_student(pk, request.user), request.user)
        return Response(attempt_payload(attempt), status=status.HTTP_201_CREATED)


class AttemptDetailAPIView(APIView):
    """The paper for an attempt, with the answers saved so far."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(attempt_detail_payload(attempt_service.own_attempt(request.user, pk)))


class AttemptAnswersAPIView(APIView):
    """Autosave: any number of answers, any number of times, until the end."""

    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        attempt = attempt_service.own_attempt(request.user, pk)
        attempt_service.end_if_access_lost(attempt, request.user)
        body = SaveAnswersSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        attempt_service.save_answers(attempt, body.validated_data["answers"])
        return Response({"saved": len(body.validated_data["answers"]), "server_time": timezone.now()})


class AttemptSubmitAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        attempt = attempt_service.submit(attempt_service.own_attempt(request.user, pk))
        return Response(submitted_payload(attempt))


class AttemptResultAPIView(APIView):
    """Score, and every question with the right answer and its explanation."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        attempt = attempt_service.own_attempt(request.user, pk)
        selectors.assert_result_visible(attempt)
        return Response(result_payload(attempt))


class AttemptSheetFilesAPIView(APIView):
    """A photo or PDF of a handwritten (CQ) answer: POST one file, or DELETE `{link}`, while the attempt is open."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request, pk, section_question_id):
        attempt = attempt_service.own_attempt(request.user, pk)
        attempt_service.end_if_access_lost(attempt, request.user)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "Choose a photo or PDF to upload."})
        sheet = attempt_service.add_sheet_file(attempt, section_question_id, upload)
        return Response({"section_question_id": sheet.section_question_id, "files": sheet.files}, status=201)

    def delete(self, request, pk, section_question_id):
        attempt = attempt_service.own_attempt(request.user, pk)
        sheet = attempt_service.remove_sheet_file(attempt, section_question_id, request.data.get("link", ""))
        return Response({"section_question_id": sheet.section_question_id, "files": sheet.files})


class ExamRankingAPIView(APIView):
    """Official results, best first, and where the caller stands."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        exam = selectors.exam_for_student(pk, request.user)
        selectors.assert_ranking_visible(exam)
        attempt_service.settled(exam.attempts.all())
        total, top, mine = selectors.ranking(exam, request.user, size=RANKING_SIZE)
        pending = selectors.pending_marking_count(exam)
        return Response(ranking_payload(total, top, mine, viewer=request.user, pending=pending))


class MyExamListAPIView(APIView):
    """Course exams the caller can sit or has sat, with where they stand on each."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        attempt_service.settled(selectors.attempts_of(request.user))
        return Response(student_exams_payload(selectors.student_exams(request.user)))
