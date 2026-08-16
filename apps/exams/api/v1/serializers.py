from rest_framework import serializers

from apps.accounts.api.v1.serializers import UserSerializer
from apps.core.api.fields import MediaField

from apps.exams.models import ExamResult, McqQuestion, McqStore


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
    """Question shape returned to a student sitting the exam.

    The correct option and its explanation are stripped unless the caller
    has already submitted an attempt. They used to be sent with the paper
    itself, so every exam was solvable from the network tab and the
    leaderboards meant nothing -- the client only hid them behind a
    `revealed` flag in the UI.

    Fails closed: with no context the answer fields are removed, so a new
    call site has to opt in deliberately.
    """

    #: Only ever exposed once an attempt exists for this user.
    ANSWER_FIELDS = ('answer', 'answer_image', 'explanation')

    source = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get('reveal_answers', False):
            for field in self.ANSWER_FIELDS:
                data.pop(field, None)
        return data

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
