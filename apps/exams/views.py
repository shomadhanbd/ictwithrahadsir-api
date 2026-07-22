from decimal import Decimal

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.pagination import LaravelStylePageNumberPagination
from apps.core.permissions import IsAdminRole
from apps.core.viewsets import AdminModelViewSet
from apps.courses.models import Content
from apps.courses.views import _user_can_access_content

from .models import ExamResult, McqQuestion, McqStore
from .serializers import (
    AdminExamResultSerializer,
    ExamMcqSerializer,
    McqQuestionSerializer,
    McqStoreSerializer,
    RankEntrySerializer,
)


def _exam_content(pk):
    content = Content.objects.filter(pk=pk, type=Content.Type.EXAM, active=True).first()
    if not content:
        raise NotFound("Exam not found.")
    return content


def _result_payload(result):
    if not result:
        return None
    return {
        "marks": result.marks,
        "positive_marks": result.positive_marks,
        "negative_marks": result.negative_marks,
        "duration": result.duration,
        "submitted": result.submitted,
        "answers": result.answers,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def exam_view(request, pk):
    if request.method == "POST":
        return exam_submit(request, pk)
    return exam_detail(request, pk)


def exam_detail(request, pk):
    content = _exam_content(pk)
    if not _user_can_access_content(request.user, content):
        raise PermissionDenied("Not subscribed")

    now = timezone.now()
    if content.exam_mode == Content.ExamMode.EXAM:
        if content.exam_start_time and now < content.exam_start_time:
            raise PermissionDenied("This exam has not started yet.")
        if content.exam_end_time and now > content.exam_end_time:
            raise PermissionDenied("This exam has ended.")

    questions = content.exam_store.all_questions() if content.exam_store else McqQuestion.objects.none()
    result = ExamResult.objects.filter(content=content, user=request.user).first()

    data = {
        "id": content.id,
        "title": content.title,
        "duration": content.exam_duration_minutes,
        "total_marks": content.exam_total_marks,
        "pass_marks": content.exam_pass_marks,
        "positive_marks": content.exam_positive_marks,
        "negative_marks": content.exam_negative_marks,
        "start_time": content.exam_start_time,
        "end_time": content.exam_end_time,
        "result_publish_time": content.exam_result_publish_time,
        "question": {
            "id": content.id,
            "exam_id": content.id,
            "body": {
                "sections": [
                    {
                        "title": content.exam_store.title if content.exam_store else content.title,
                        "required": True,
                        "questions": ExamMcqSerializer(questions, many=True).data,
                    }
                ],
                "max_sections": 1,
            },
        },
        "result": _result_payload(result),
    }
    return Response(data)


def exam_submit(request, pk):
    content = _exam_content(pk)
    if not _user_can_access_content(request.user, content):
        raise PermissionDenied("Not subscribed")
    if ExamResult.objects.filter(content=content, user=request.user).exists():
        raise ValidationError({"exam": ["You have already submitted this exam."]})

    sections = request.data.get("sections", [])
    if not isinstance(sections, list):
        raise ValidationError({"sections": ["Must be a list."]})

    positive = content.exam_positive_marks or Decimal("1")
    negative = content.exam_negative_marks or Decimal("0")
    total_marks = Decimal("0")
    for section in sections:
        for answer in section.get("answers", []):
            mcq = McqQuestion.objects.filter(pk=answer.get("mcq_id")).first()
            user_answer = (answer.get("user_answer") or "").strip().lower()
            if not mcq or not user_answer:
                continue
            if user_answer == mcq.answer:
                total_marks += positive
            else:
                total_marks -= negative

    duration = int(request.data.get("duration") or 0)
    result = ExamResult.objects.create(
        content=content,
        user=request.user,
        marks=total_marks,
        positive_marks=positive,
        negative_marks=negative,
        duration=duration,
        submitted=True,
        answers=sections,
    )
    return Response(_result_payload(result), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exam_ranking(request, pk):
    content = _exam_content(pk)
    results = ExamResult.objects.filter(content=content).select_related("user").order_by("-marks", "duration")
    user_result = results.filter(user=request.user).first()
    user_rank = None
    if user_result:
        user_rank = list(results.values_list("id", flat=True)).index(user_result.id) + 1

    return Response(
        {
            "exam_title": content.title,
            "user_rank": user_rank,
            "user_result": RankEntrySerializer(user_result).data if user_result else None,
            "rankings": RankEntrySerializer(results[:100], many=True).data,
        }
    )


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------


class AdminMcqStoreViewSet(AdminModelViewSet):
    queryset = McqStore.objects.all()
    serializer_class = McqStoreSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        mcq_store_id = self.request.query_params.get("mcq_store_id")
        if mcq_store_id:
            qs = qs.filter(mcq_store_id=mcq_store_id)
        elif self.action == "list":
            qs = qs.filter(mcq_store__isnull=True)
        return qs


class AdminMcqQuestionViewSet(AdminModelViewSet):
    queryset = McqQuestion.objects.all()
    serializer_class = McqQuestionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        mcq_store_id = self.request.query_params.get("mcq_store_id")
        if mcq_store_id:
            qs = qs.filter(mcq_store_id=mcq_store_id)
        return qs


@api_view(["GET"])
@permission_classes([IsAdminRole])
def admin_exam_results(request):
    exam_id = request.query_params.get("exam_id")
    qs = ExamResult.objects.select_related("user", "content")
    if exam_id:
        qs = qs.filter(content_id=exam_id)
    paginator = LaravelStylePageNumberPagination()
    page = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response(AdminExamResultSerializer(page, many=True).data)
