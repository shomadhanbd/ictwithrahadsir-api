from datetime import UTC

from rest_framework import serializers

from apps.assessment.models import ExamAttempt, Question, QuestionBank
from apps.core.api.fields import MediaField
from apps.identity.api.v1.serializers import UserSerializer


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

    def get_user(self, obj) -> dict | None:
        return {
            "id": obj.user_id,
            "name": obj.user.name,
            "institution": obj.user.institution,
            "image": obj.user.image,
        }


class ExamSubmissionRequestSerializer(serializers.Serializer):
    """The body of a paper being handed in.

    `sections` is passed through as-is rather than being modelled field by
    field: it is stored verbatim on `ExamAttempt.answers` so a paper can be
    re-displayed exactly as the student left it, and the marker already
    tolerates any junk inside it.
    """

    sections = serializers.ListField(
        child=serializers.JSONField(), required=False, default=list,
        error_messages={'not_a_list': 'Must be a list.'},
    )
    duration = serializers.IntegerField(required=False, default=0, min_value=0)

    def validate_sections(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Must be a list.')
        return value

    def validate_duration(self, value):
        return value or 0


class ExamResultSerializer(serializers.ModelSerializer):
    """A student's own attempt, as embedded in the exam paper payload.

    Six fields only: this is the
    `result` block inside `/exams/<id>/`, and its key list is contract.

    The mark fields are `FloatField`, not `DecimalField`. They are `Decimal`
    on the model, and DRF's JSON encoder has always rendered them as JSON
    *numbers* here; `DecimalField` would turn them into strings such as
    "3.00" and break every client that does arithmetic on them.
    """

    marks = serializers.FloatField()
    positive_marks = serializers.FloatField()
    negative_marks = serializers.FloatField()

    class Meta:
        model = ExamAttempt
        fields = [
            "marks",
            "positive_marks",
            "negative_marks",
            "duration",
            "submitted",
            "answers",
        ]


class ExamPaperSerializer(serializers.Serializer):
    """Everything `/exams/<id>/` returns: the paper plus this user's attempt.

    Replaces a 38-line dict literal that lived in the view. The nesting under
    `question.body.sections` mirrors a multi-section exam format the models do
    not actually have -- `max_sections` is always 1 and `required` always true
    -- but it is the shape the client parses, so it is reproduced exactly.

    `total_marks`/`pass_marks` are `IntegerField` and the two per-question
    marks are `FloatField`, matching the model's own column types; getting
    that pairing wrong is what silently changes `15` into `15.0`.
    """

    id = serializers.IntegerField(source="content.id")
    title = serializers.CharField(source="content.title")
    duration = serializers.IntegerField(source="duration_minutes", allow_null=True)
    total_marks = serializers.IntegerField(allow_null=True)
    pass_marks = serializers.IntegerField(allow_null=True)
    positive_marks = serializers.FloatField(allow_null=True)
    negative_marks = serializers.FloatField(allow_null=True)
    # `default_timezone=utc` is load-bearing. DRF's DateTimeField renders in
    # the *current* timezone, which is Asia/Dhaka here, so these would go out
    # as "2026-08-09T19:47:26.133162+06:00". They have always gone out as UTC
    # with a Z suffix, because the view passed raw datetimes to DRF's JSON
    # encoder. Same instant either way, different string -- and a client that
    # compares or slices the string would break.
    start_time = serializers.DateTimeField(allow_null=True, default_timezone=UTC)
    end_time = serializers.DateTimeField(allow_null=True, default_timezone=UTC)
    result_publish_time = serializers.DateTimeField(
        allow_null=True, default_timezone=UTC
    )
    #: Lets the client say "results not published yet" rather than silently
    #: showing an unmarked review paper.
    #: Note the singular key against the plural property -- the payload has
    #: always said `result_published` and the model says `results_published`.
    result_published = serializers.BooleanField(source="results_published")
    question = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()

    def get_question(self, exam) -> dict | None:
        bank = exam.question_bank
        return {
            "id": exam.content_id,
            "exam_id": exam.content_id,
            "body": {
                "sections": [
                    {
                        "title": bank.title if bank else exam.content.title,
                        "required": True,
                        "questions": ExamMcqSerializer(
                            self.context["questions"],
                            many=True,
                            context=self.context,
                        ).data,
                    }
                ],
                "max_sections": 1,
            },
        }

    def get_result(self, exam) -> dict | None:
        attempt = self.context.get("attempt")
        return ExamResultSerializer(attempt).data if attempt else None


class ExamRankingSerializer(serializers.Serializer):
    """The leaderboard for one exam, plus the caller's own standing.

    The board is everybody else's marks, so it is the thing the publish time
    most clearly governs: before results are published `rankings` is empty
    and `user_rank` is null, while `user_result` stays -- the caller already
    knows how they did. The response keeps its shape either way, so the
    client degrades to an empty board rather than to an error.
    """

    exam_title = serializers.CharField()
    user_rank = serializers.IntegerField(allow_null=True)
    user_result = RankEntrySerializer(allow_null=True)
    rankings = RankEntrySerializer(many=True)
    result_published = serializers.BooleanField()
    # UTC with a Z suffix, as the raw encoder produced. DRF's DateTimeField
    # would otherwise render Asia/Dhaka's +06:00 -- same instant, different
    # string, and a client that slices or compares it would break.
    result_publish_time = serializers.DateTimeField(
        allow_null=True, default_timezone=UTC
    )
