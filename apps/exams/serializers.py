from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.core.fields import MediaField

from .models import ExamResult, McqQuestion, McqStore


class McqStoreSerializer(serializers.ModelSerializer):
    mcq_store_id = serializers.PrimaryKeyRelatedField(
        source="mcq_store", queryset=McqStore.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = McqStore
        fields = ["id", "title", "mcq_store_id", "order"]
        read_only_fields = ["id"]


class McqQuestionSerializer(serializers.ModelSerializer):
    question_image = MediaField(upload_to="mcq", required=False)
    answer_image = MediaField(upload_to="mcq", required=False)
    mcq_store_id = serializers.PrimaryKeyRelatedField(source="mcq_store", queryset=McqStore.objects.all())

    class Meta:
        model = McqQuestion
        fields = [
            "id",
            "mcq_store_id",
            "question",
            "question_image",
            "a",
            "b",
            "c",
            "d",
            "e",
            "answer",
            "answer_image",
            "explanation",
            "source_year",
            "source_board",
            "source_topic",
            "source_chapter",
            "source_college",
            "source_subject",
        ]
        read_only_fields = ["id"]


class ExamMcqSerializer(serializers.ModelSerializer):
    """Question shape returned to a student sitting the exam -- everything
    the McqQuestion has, matching the client's `ExamMcq` type exactly."""

    source = serializers.SerializerMethodField()

    class Meta:
        model = McqQuestion
        fields = [
            "id",
            "question",
            "question_image",
            "a",
            "b",
            "c",
            "d",
            "e",
            "answer",
            "answer_image",
            "explanation",
            "source",
        ]

    def get_source(self, obj):
        return {
            "year": obj.source_year,
            "board": obj.source_board,
            "topic": obj.source_topic,
            "chapter": obj.source_chapter,
            "college": obj.source_college,
            "subject": obj.source_subject,
        }


class ExamResultSerializer(serializers.ModelSerializer):
    exam_id = serializers.PrimaryKeyRelatedField(source="content", read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(source="user", read_only=True)

    class Meta:
        model = ExamResult
        fields = [
            "id",
            "exam_id",
            "user_id",
            "marks",
            "positive_marks",
            "negative_marks",
            "duration",
            "submitted",
            "answers",
            "attachment",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AdminExamResultSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    exam_id = serializers.PrimaryKeyRelatedField(source="content", read_only=True)
    exam_title = serializers.CharField(source="content.title", read_only=True)

    class Meta:
        model = ExamResult
        fields = [
            "id",
            "exam_id",
            "exam_title",
            "user",
            "marks",
            "positive_marks",
            "negative_marks",
            "duration",
            "created_at",
        ]


class RankEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamResult
        fields = ["id", "user", "duration", "marks"]

    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return {
            "id": obj.user_id,
            "name": obj.user.name,
            "institution": obj.user.institution,
            "image": obj.user.image,
        }
