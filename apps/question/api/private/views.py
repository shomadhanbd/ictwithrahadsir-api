from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.auth.permissions import IsTeachingStaff
from apps.question import kinds, selectors, services
from apps.question.api.private.filters import QuestionBlockFilter
from apps.question.api.private.serializers import (
    AdminQuestionBlockSerializer,
    AdminQuestionSerializer,
    QuestionBlockSaveRequestSerializer,
    QuestionKindSerializer,
    QuestionSourceSerializer,
)
from apps.question.models import QuestionBlock, QuestionSource


class AdminQuestionBlockListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminQuestionBlockSerializer
    queryset = selectors.admin_blocks()
    search_fields = [
        "question_set__stimulus_content",
        "question_set__questions__prompt_content",
        "standalone_question__prompt_content",
        "sources__name",
    ]
    filterset_class = QuestionBlockFilter


class AdminQuestionBlockDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = AdminQuestionBlockSerializer
    queryset = selectors.admin_blocks()


class AdminQuestionBlockSaveAPIView(APIView):
    """Saves a block with its questions in one transaction: a part the rules refuse (options on a published
    paper, an exam that is not the caller's) leaves nothing half-saved, the block included."""

    permission_classes = [IsTeachingStaff]

    def post(self, request):
        body = QuestionBlockSaveRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        context = {"request": request}
        with transaction.atomic():
            existing = get_object_or_404(QuestionBlock, pk=data["block_id"]) if data.get("block_id") else None
            block_form = AdminQuestionBlockSerializer(
                existing, data=data["block"], partial=existing is not None, context=context
            )
            block_form.is_valid(raise_exception=True)
            block = block_form.save()
            owner = (
                {"question_set_id": block.question_set.pk}
                if block.kind == QuestionBlock.Kind.GROUP
                else {"block_id": block.pk}
            )
            parts = selectors.block_questions_by_id(block)
            for index, payload in enumerate(data["questions"]):
                question = parts.get(payload.get("id")) if payload.get("id") else None
                if payload.get("id") and question is None:
                    raise ValidationError({"questions": [f"Part {index + 1} is not a part of this question."]})
                form = AdminQuestionSerializer(
                    question, data={**payload, **owner}, partial=question is not None, context=context
                )
                if not form.is_valid():
                    raise ValidationError(_numbered(form.errors, index))
                form.save()
            for question_id in data["removed_question_ids"]:
                if question_id in parts:
                    services.delete_question(parts[question_id])
        block = selectors.admin_blocks().get(pk=block.pk)
        return Response(AdminQuestionBlockSerializer(block, context=context).data)


def _numbered(errors, index) -> dict:
    """A part's field errors, each said of "Part N" so the dialog can show which part was refused."""
    return {
        field: [f"Part {index + 1}: {message}" for message in (messages if isinstance(messages, list) else [messages])]
        for field, messages in errors.items()
    }


class AdminQuestionSourceListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = QuestionSourceSerializer
    queryset = QuestionSource.objects.all()
    search_fields = ["name", "unit"]
    filterset_fields = ["kind", "year", "is_active"]


class AdminQuestionSourceDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaff]
    serializer_class = QuestionSourceSerializer
    queryset = QuestionSource.objects.all()


class AdminQuestionTypeListAPIView(APIView):
    """The question types this bank knows about, and what each can do."""

    permission_classes = [IsTeachingStaff]
    serializer_class = QuestionKindSerializer

    def get(self, request):
        return Response({"data": QuestionKindSerializer(list(kinds.REGISTRY.values()), many=True).data})


class AdminRefreshQuestionCountsAPIView(APIView):
    permission_classes = [IsTeachingStaff]

    def post(self, request):
        services.refresh_curriculum_question_counts()
        return Response({"ok": True})
