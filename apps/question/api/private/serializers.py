from rest_framework import serializers

from apps.academic.models import Chapter, Subject, Topic
from apps.question import services, validators
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet, QuestionSource
from apps.question.selectors import owning_block


class AdminOptionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = QuestionOption
        fields = ["id", "label", "content", "is_correct", "position"]


class AdminQuestionSerializer(serializers.ModelSerializer):
    """Options are written with their question, never apart.

    Question and option text is plain text, rendered as text by both frontends, so it is stored verbatim:
    running it through `clean_html` would turn "x < 5" into "x &lt; 5".
    """

    options = AdminOptionSerializer(many=True, required=False)
    block_id = serializers.PrimaryKeyRelatedField(
        source="block", queryset=QuestionBlock.objects.all(), required=False, allow_null=True
    )
    question_set_id = serializers.PrimaryKeyRelatedField(
        source="question_set", queryset=QuestionSet.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Question
        fields = [
            "id",
            "slug",
            "block_id",
            "question_set_id",
            "question_type",
            "metadata",
            "label",
            "marks",
            "order_in_set",
            "prompt_content",
            "model_answer",
            "explanation",
            "options",
        ]
        read_only_fields = ["slug"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None:
            owner = owning_block(block=self.instance.block, question_set=self.instance.question_set)
            validators.validate_editor(self.context["request"].user, owner)
        return validators.validate_question_write(
            self.instance, attrs, options_after_write=self._options_after_write(attrs)
        )

    def _options_after_write(self, attrs):
        if "options" in attrs:
            return attrs["options"]
        if self.instance is None:
            return []
        return [
            {"is_correct": option.is_correct, "position": option.position} for option in self.instance.options.all()
        ]

    def create(self, validated_data):
        return services.create_question(validated_data)

    def update(self, instance, validated_data):
        return services.update_question(instance, validated_data)


class AdminQuestionSetSerializer(serializers.ModelSerializer):
    """Written nested in its block; it has no endpoint of its own."""

    questions = AdminQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = QuestionSet
        fields = ["id", "slug", "stimulus_type", "stimulus_content", "questions"]
        read_only_fields = ["slug"]


class QuestionKindSerializer(serializers.Serializer):
    """`apps.question.kinds`, served so clients need not hardcode the types."""

    value = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    uses_options = serializers.BooleanField(read_only=True)
    auto_graded = serializers.BooleanField(read_only=True)
    option_meaning = serializers.CharField(read_only=True)


class QuestionSourceSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)

    class Meta:
        model = QuestionSource
        fields = ["id", "slug", "kind", "name", "year", "unit", "label", "is_active"]
        read_only_fields = ["slug"]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        validators.validate_source_unique(self.instance, attrs)
        return attrs


class AdminQuestionBlockSerializer(serializers.ModelSerializer):
    subject_id = serializers.PrimaryKeyRelatedField(source="subject", queryset=Subject.objects.all())
    chapter_id = serializers.PrimaryKeyRelatedField(
        source="chapter", queryset=Chapter.objects.all(), required=False, allow_null=True
    )
    topic_ids = serializers.PrimaryKeyRelatedField(
        source="topics", queryset=Topic.objects.all(), many=True, required=False
    )
    source_ids = serializers.PrimaryKeyRelatedField(
        source="sources", queryset=QuestionSource.objects.all(), many=True, required=False
    )
    sources = QuestionSourceSerializer(many=True, read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    chapter_name = serializers.CharField(source="chapter.name", read_only=True, default=None)

    question_set = AdminQuestionSetSerializer(required=False, allow_null=True)
    standalone_question = AdminQuestionSerializer(read_only=True)

    class Meta:
        model = QuestionBlock
        fields = [
            "id",
            "slug",
            "kind",
            "subject_id",
            "subject_name",
            "chapter_id",
            "chapter_name",
            "topic_ids",
            "order_in_chapter",
            "question_count",
            "source_ids",
            "sources",
            "is_active",
            "question_set",
            "standalone_question",
        ]
        read_only_fields = ["slug", "question_count"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", QuestionBlock.Kind.STANDALONE))
        if "topics" in attrs:
            topics = attrs["topics"]
        else:
            topics = list(self.instance.topics.all()) if self.instance is not None else []
        if self.instance is not None:
            validators.validate_editor(self.context["request"].user, self.instance)
        validators.validate_block_change(self.instance, subject=subject, kind=kind)
        validators.validate_block(
            subject=subject,
            chapter=attrs.get("chapter", getattr(self.instance, "chapter", None)),
            kind=kind,
            topics=topics,
            has_set=bool(attrs.get("question_set")) or bool(getattr(self.instance, "question_set", None)),
            has_standalone=bool(getattr(self.instance, "standalone_question", None)),
        )
        return attrs

    def create(self, validated_data):
        return services.save_block(None, validated_data)

    def update(self, instance, validated_data):
        return services.save_block(instance, validated_data)


class QuestionBlockSaveRequestSerializer(serializers.Serializer):
    """`POST question-blocks/save/`: a block, its questions and the questions removed from it, in one go."""

    block_id = serializers.IntegerField(required=False, allow_null=True, help_text="Omit to create the block.")
    block = serializers.DictField(help_text="The block's fields, as `question-blocks/` takes them.")
    questions = serializers.ListField(
        child=serializers.DictField(),
        help_text="Each part, as `questions/` takes it; an `id` edits that part. Its owner is set from the block.",
    )
    removed_question_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
