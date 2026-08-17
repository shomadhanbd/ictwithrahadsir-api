from rest_framework import serializers

from apps.identity.api.v1.serializers import UserSerializer
from apps.core.api.fields import MediaField

from apps.assessment.models import ExamAttempt, Question, QuestionBank


class QuestionBankSerializer(serializers.ModelSerializer):
    mcq_store_id = serializers.PrimaryKeyRelatedField(
        source="parent", queryset=QuestionBank.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = QuestionBank
        fields = ["id", "title", "mcq_store_id", "order"]
        read_only_fields = ["id"]


class QuestionSerializer(serializers.ModelSerializer):
    question_image = MediaField(upload_to="mcq", required=False)
    answer_image = MediaField(upload_to="mcq", required=False)
    # The admin panel sends `mcq_store_id`; only the model field behind
    # it was renamed.
    mcq_store_id = serializers.PrimaryKeyRelatedField(source="bank", queryset=QuestionBank.objects.all())

    class Meta:
        model = Question
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


class PracticeQuestionSerializer(serializers.ModelSerializer):
    """A question in the free practice quiz.

    Carries the answer and the explanation, unlike `ExamMcqSerializer`, which
    strips them: nothing is being scored here and the explanation is the whole
    point — a practice question that cannot tell you why you were wrong is
    just a quiz. Scraping the bank wholesale is held off by the sample cap on
    the view rather than by hiding the answer, which would make the feature
    useless.
    """

    question_image = MediaField(upload_to="mcq", required=False)
    answer_image = MediaField(upload_to="mcq", required=False)

    class Meta:
        model = Question
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
            "source_year",
            "source_board",
        ]
        read_only_fields = fields


class PracticeBankSerializer(serializers.ModelSerializer):
    """A practice topic, with how many questions sit under it."""

    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = QuestionBank
        fields = ["id", "title", "question_count"]
        read_only_fields = fields


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
        model = Question
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


class ExamAttemptSerializer(serializers.ModelSerializer):
    exam_id = serializers.PrimaryKeyRelatedField(source="exam", read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(source="user", read_only=True)

    class Meta:
        model = ExamAttempt
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


class AdminExamAttemptSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    exam_id = serializers.PrimaryKeyRelatedField(source="exam", read_only=True)
    exam_title = serializers.CharField(source="exam.content.title", read_only=True)

    class Meta:
        model = ExamAttempt
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
        model = ExamAttempt
        fields = ["id", "user", "duration", "marks"]

    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        return {
            "id": obj.user_id,
            "name": obj.user.name,
            "institution": obj.user.institution,
            "image": obj.user.image,
        }
