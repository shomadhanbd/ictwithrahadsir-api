"""Two serializer families, deliberately separated.

The `Admin*` ones carry `is_correct`, `model_answer` and `explanation` -- the
answer key. The reference app served those from an `AllowAny` feed, so anyone
could read the answer to every exam question. **No public endpoint may use an
`Admin*` serializer**; the plain ones exist for that feed when it is built.
"""

from django.db import transaction
from django.db.models import F

from rest_framework import serializers

from apps.academic.models import Chapter, Subject, Topic
from apps.question import services, types
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet, QuestionSource

# -- options -----------------------------------------------------------------


class OptionSerializer(serializers.ModelSerializer):
    """Public: what a student may see."""

    class Meta:
        model = QuestionOption
        fields = ["id", "label", "content", "position"]


class AdminOptionSerializer(serializers.ModelSerializer):
    #: Writable, unlike the usual read-only pk: an update sends the whole list
    #: back, and the `id` is how a row is recognised as the one already there
    #: rather than a replacement for it.
    id = serializers.IntegerField(required=False)

    class Meta:
        model = QuestionOption
        fields = ["id", "label", "content", "is_correct", "position"]


# -- questions ---------------------------------------------------------------


class QuestionSerializer(serializers.ModelSerializer):
    """Public: no answer key."""

    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = [
            "id",
            "slug",
            "question_type",
            "metadata",
            "label",
            "marks",
            "order_in_set",
            "prompt_content",
            "options",
        ]


class AdminQuestionSerializer(serializers.ModelSerializer):
    """Options are written with their question -- they are never authored apart."""

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
        block = attrs.get("block", getattr(self.instance, "block", None))
        question_set = attrs.get("question_set", getattr(self.instance, "question_set", None))
        if bool(block) == bool(question_set):
            raise serializers.ValidationError("Give the question either a block or a question set, not both.")

        services.validate_owner_kind(block=block, question_set=question_set)

        owner = services.owning_block(block=block, question_set=question_set)
        if self.instance is None:
            services.validate_parts_change(owner)
            services.validate_new_part_type(owner, attrs.get("question_type", Question.Type.MCQ))
        else:
            previous = services.owning_block(block=self.instance.block, question_set=self.instance.question_set)
            if previous != owner:
                # A move is a removal from one block and an addition to another.
                services.validate_parts_change(previous)
                services.validate_parts_change(owner)
            services.validate_type_change(
                owner,
                before=self.instance.question_type,
                after=attrs.get("question_type", self.instance.question_type),
            )

        question_type = attrs.get("question_type", getattr(self.instance, "question_type", Question.Type.MCQ))
        if "metadata" in attrs or self.instance is None:
            # Stored already normalised: a client that omits `select_mode` gets
            # the declared default rather than an empty dict nothing can read.
            attrs["metadata"] = types.clean_metadata(question_type, attrs.get("metadata"))
        services.validate_question(
            question_type=attrs.get("question_type", getattr(self.instance, "question_type", Question.Type.MCQ)),
            metadata=attrs.get("metadata", getattr(self.instance, "metadata", None)),
            options=self._options_after_write(attrs),
        )
        return attrs

    def _options_after_write(self, attrs):
        """The options the question will have once this write lands.

        A PATCH that only touches the prompt does not mention options, and
        validating the empty list rejected it for having no correct answer --
        an edit refused over data the request never proposed to change.
        """
        if "options" in attrs:
            return attrs["options"]
        if self.instance is None:
            return []
        return [
            {"is_correct": option.is_correct, "position": option.position} for option in self.instance.options.all()
        ]

    # `question_count` is not touched here: `apps.question.signals` keeps it in
    # step for every path, this one included.

    @transaction.atomic
    def create(self, validated_data):
        options = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        QuestionOption.objects.bulk_create(
            QuestionOption(question=question, **self._option_fields(option)) for option in options
        )
        return question

    @transaction.atomic
    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if options is not None:
            self._sync_options(instance, options)
        return instance

    @staticmethod
    def _option_fields(option):
        return {field: value for field, value in option.items() if field != "id"}

    def _sync_options(self, question, payloads):
        """Update the rows that are still there, add the new ones, drop the rest.

        The previous version deleted every option and recreated it, so editing
        a prompt handed each option a new id. Nothing depends on those ids yet;
        a submission's `selected_option` will, and by then the damage would be
        answers pointing at rows that no longer exist.
        """
        existing = {option.pk: option for option in question.options.all()}

        incoming = []
        for payload in payloads:
            option = existing.get(payload.get("id")) or QuestionOption(question=question)
            for field, value in self._option_fields(payload).items():
                setattr(option, field, value)
            incoming.append(option)

        kept = {option.pk for option in incoming if option.pk}
        question.options.exclude(pk__in=kept).delete()

        # `(question, position)` is unique and checked per statement, so writing
        # the survivors one at a time collides the moment two of them swap
        # places. Park them above every final position first -- one extra
        # UPDATE, and no id is lost to a reshuffle.
        if kept:
            ceiling = max([option.position for option in incoming] + [existing[pk].position for pk in kept]) + 1
            question.options.filter(pk__in=kept).update(position=F("position") + ceiling)

        for option in incoming:
            option.save()


# -- stimulus sets -----------------------------------------------------------


class QuestionSetSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = QuestionSet
        fields = ["id", "slug", "stimulus_type", "stimulus_content", "questions"]


class AdminQuestionSetSerializer(serializers.ModelSerializer):
    """Writable, and nested in the block rather than given its own endpoint.

    A stimulus has no life apart from the group block it belongs to -- it
    cannot exist before one or move to another -- so authoring it in the same
    request is both fewer round trips and one fewer way to end up with a group
    block that has no stimulus. Until this it was read-only with no endpoint
    anywhere, which meant creative questions could not be authored at all.
    """

    questions = AdminQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = QuestionSet
        fields = ["id", "slug", "stimulus_type", "stimulus_content", "questions"]
        read_only_fields = ["slug"]


# -- the type registry -------------------------------------------------------


class QuestionKindSerializer(serializers.Serializer):
    """`apps.question.types`, served so clients stop hardcoding the types.

    Every `<option value="mcq">` in a UI is a place that has to be found and
    edited when a ninth type arrives. This is the list to render instead.
    """

    value = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    uses_options = serializers.BooleanField(read_only=True)
    auto_graded = serializers.BooleanField(read_only=True)
    option_meaning = serializers.CharField(read_only=True)


# -- provenance --------------------------------------------------------------


class QuestionSourceSerializer(serializers.ModelSerializer):
    """Public-safe: provenance carries no part of the answer key."""

    label = serializers.CharField(read_only=True)

    class Meta:
        model = QuestionSource
        fields = ["id", "slug", "kind", "name", "year", "unit", "label", "is_active"]
        read_only_fields = ["slug"]
        #: DRF builds a `UniqueTogetherValidator` out of the model constraint,
        #: and that validator forces every column it covers to be required --
        #: so an undated board paper could not be recorded without inventing a
        #: `year` and a `unit`. It also cannot express the partial constraint
        #: that catches undated duplicates. Both are handled in `validate`.
        validators = []

    #: What the row falls back to when the request leaves a column out. Taken
    #: from the model's own defaults, so the check compares the row that will
    #: actually be written -- `unit` is "", never NULL.
    DEFAULTS = {"kind": QuestionSource.Kind.BOARD, "name": "", "year": None, "unit": ""}

    def validate(self, attrs):
        attrs = super().validate(attrs)

        row = {}
        for field, default in self.DEFAULTS.items():
            if field in attrs:
                row[field] = attrs[field]
            elif self.instance is not None:
                row[field] = getattr(self.instance, field)
            else:
                row[field] = default

        clash = QuestionSource.objects.filter(**row)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"name": "That exam is already recorded."})
        return attrs


# -- blocks ------------------------------------------------------------------


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
        services.validate_block_change(self.instance, subject=subject, kind=kind)
        services.validate_block(
            subject=subject,
            chapter=attrs.get("chapter", getattr(self.instance, "chapter", None)),
            kind=kind,
            topics=topics,
            #: Reads the request too, not only the stored row: on create the
            #: instance has no stimulus yet, so checking the instance alone let
            #: a standalone block be handed one in the very same request.
            has_set=bool(attrs.get("question_set")) or bool(getattr(self.instance, "question_set", None)),
            has_standalone=bool(getattr(self.instance, "standalone_question", None)),
        )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        question_set = validated_data.pop("question_set", None)
        block = super().create(validated_data)
        self._write_question_set(block, question_set)
        return block

    @transaction.atomic
    def update(self, instance, validated_data):
        missing = object()
        question_set = validated_data.pop("question_set", missing)
        block = super().update(instance, validated_data)
        if question_set is not missing:
            self._write_question_set(block, question_set)
        return block

    @staticmethod
    def _write_question_set(block, data):
        """Edited in place rather than replaced: the stimulus owns the block's
        questions, so recreating it would cascade them all away."""
        if data is None:
            return

        existing = QuestionSet.objects.filter(block=block).first()
        if existing is None:
            existing = QuestionSet.objects.create(block=block, **data)
        else:
            for field, value in data.items():
                setattr(existing, field, value)
            existing.save()

        # The detail queryset prefetches `question_set`, so the instance is
        # still holding the row as it was *before* this write and the response
        # would echo the old stimulus back at whoever just edited it.
        block._state.fields_cache.pop("question_set", None)
        block._prefetched_objects_cache = {}
