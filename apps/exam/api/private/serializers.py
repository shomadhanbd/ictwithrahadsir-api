"""Admin serializers for exam authoring.

`created_by` is read-only everywhere and set from the token in
`perform_create`, so a forged `created_by_id` in a payload is discarded before
it reaches `validated_data`.

The exam detail nests its sections read-only, but **not** the question bank's
block tree -- that payload carries the answer key and belongs behind the bulk
picker endpoint, not in every exam row.
"""

import copy

from django.db import transaction

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.academic.models import Batch, Subject
from apps.exam import services
from apps.exam.api.private.permissions import assert_may_author_exam
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.question.models import QuestionBlock


class MergedAttrsMixin:
    """Reads a field as it will be once this request is applied.

    A PATCH carries only what changed, but these rules are about combinations
    -- `pass_marks` against `marks`, `negative_marks` against
    `marks_per_question` -- so a rule needs the values the request *omitted*
    read off the stored row. On a create there is no row, so it falls through
    to the default instead.

    Written out per field that is
    `attrs.get("marks", getattr(self.instance, "marks", None))`, which ran to
    seven near-identical lines inside one call and buried which argument was
    actually interesting.
    """

    def merged(self, attrs):
        """Returns `after(field, default=None)` bound to this request."""

        def after(field, default=None):
            return attrs.get(field, getattr(self.instance, field, default))

        return after


# -- picks -------------------------------------------------------------------


class AdminExamSectionQuestionSerializer(MergedAttrsMixin, serializers.ModelSerializer):
    section_id = serializers.PrimaryKeyRelatedField(source="section", queryset=ExamSection.objects.all())
    block_id = serializers.PrimaryKeyRelatedField(source="block", queryset=QuestionBlock.objects.all())

    class Meta:
        model = ExamSectionQuestion
        fields = ["id", "section_id", "block_id", "marks", "order"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        after = self.merged(attrs)
        section = after("section")
        block = after("block")

        # Fixed once placed. The freeze below only sees where a pick is *going*,
        # so moving one out of a published paper into a draft emptied the
        # published one; there is no real reason to move a pick anyway.
        if self.instance is not None and "section" in attrs and attrs["section"] != self.instance.section:
            raise serializers.ValidationError({"section_id": "A question cannot be moved to another section."})

        # A POST here fetches no object, so DRF runs no object permission.
        assert_may_author_exam(self.context["request"], section.exam)
        services.validate_paper_is_editable(section.exam)

        if block is not None:
            services.validate_section_blocks(section=section, blocks=[block])
        if attrs.get("marks") is None and self.instance is None and block is not None:
            # The same default as the bulk picker: what the block asks of a
            # student, not a flat rate per item.
            attrs["marks"] = services.block_question_count(block, section.question_type) * (section.marks_per_question)
        return attrs


class ExamSectionQuestionRowSerializer(serializers.ModelSerializer):
    """The lightweight row nested in an exam's detail."""

    class Meta:
        model = ExamSectionQuestion
        fields = ["id", "block_id", "marks", "order"]


# -- sections ----------------------------------------------------------------


class AdminExamSectionSerializer(MergedAttrsMixin, serializers.ModelSerializer):
    exam_id = serializers.PrimaryKeyRelatedField(source="exam", queryset=Exam.objects.all())
    exam_title = serializers.CharField(source="exam.title", read_only=True)
    subject_id = serializers.PrimaryKeyRelatedField(source="subject", queryset=Subject.objects.all())
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = ExamSection
        fields = [
            "id",
            "exam_id",
            "exam_title",
            "title",
            "question_type",
            "subject_id",
            "subject_name",
            "marks",
            "marks_per_question",
            "negative_marks",
            "pass_marks",
            "required_question_count",
            "duration_minutes",
            "instructions",
            "order",
            "shuffle_questions",
            "shuffle_options",
            "question_count",
            "computed_marks",
        ]
        read_only_fields = ["question_count", "computed_marks"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        after = self.merged(attrs)

        exam = after("exam")
        # Fixed once created, for the same reason as a pick's section: moving a
        # section out of a published paper went past the freeze.
        if self.instance is not None and "exam" in attrs and attrs["exam"] != self.instance.exam:
            raise serializers.ValidationError({"exam_id": "A section cannot be moved to another exam."})
        assert_may_author_exam(self.context["request"], exam)
        services.validate_paper_is_editable(exam)

        question_type = after("question_type", ExamSection.Type.MCQ)
        subject = after("subject")

        if self.instance is not None:
            # The type and subject rules, guarded from the section's side too:
            # refusing a wrong block is only half of the same invariant.
            services.validate_question_type_change(section=self.instance, question_type=question_type)
            services.validate_section_subject_change(section=self.instance, subject=subject)

        services.validate_section(
            exam=exam,
            question_type=question_type,
            subject=subject,
            marks=after("marks"),
            marks_per_question=after("marks_per_question"),
            duration_minutes=after("duration_minutes"),
            required_question_count=after("required_question_count"),
            negative_marks=after("negative_marks"),
            pass_marks=after("pass_marks"),
            shuffle_options=after("shuffle_options", False),
            instance=self.instance,
        )
        return attrs


class ExamSectionRowSerializer(serializers.ModelSerializer):
    """Nested in the exam detail, with its picks but not the block tree."""

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    section_questions = ExamSectionQuestionRowSerializer(many=True, read_only=True)
    target_marks = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)

    class Meta:
        model = ExamSection
        fields = [
            "id",
            "title",
            "question_type",
            "subject_id",
            "subject_name",
            "marks",
            "marks_per_question",
            "negative_marks",
            "pass_marks",
            "required_question_count",
            "duration_minutes",
            "instructions",
            "order",
            "shuffle_questions",
            "shuffle_options",
            "question_count",
            "computed_marks",
            "target_marks",
            "section_questions",
        ]


# -- the paper header --------------------------------------------------------


class ExamPaperPartSerializer(serializers.Serializer):
    """One part's line in the printed header."""

    section_id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    instructions = serializers.CharField(read_only=True, allow_blank=True)
    question_type = serializers.ChoiceField(choices=ExamSection.Type.choices, read_only=True)
    question_type_label = serializers.CharField(read_only=True)
    subject_name = serializers.CharField(read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True, allow_null=True)
    questions_given = serializers.IntegerField(read_only=True)
    answers_required = serializers.IntegerField(read_only=True)
    marks_per_question = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True)
    marks = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    computed_marks = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    target_marks = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    shows_multiplication = serializers.BooleanField(read_only=True)
    #: The **resolved** rate, not the stored column -- a `null` on the section
    #: row is the exam's rate here, and a CQ part is always 0.
    negative_marks = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True)
    pass_marks = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)
    problems = serializers.ListField(child=serializers.CharField(), read_only=True)


class ExamPaperHeaderSerializer(serializers.Serializer):
    """What the top of the প্রশ্নপত্র says.

    A declared serializer given the exam itself via `source="*"`, rather than a
    `SerializerMethodField` returning the dict raw. Two reasons, both of which
    bite otherwise: DRF's encoder renders a raw `Decimal` as the float `1.0`
    while every other money field on the same response is the string `"1.00"`
    (`COERCE_DECIMAL_TO_STRING`), and an untyped method field generates as an
    opaque `object` in the schema.
    """

    title = serializers.CharField(read_only=True)
    instructions = serializers.CharField(read_only=True)
    duration_minutes = serializers.IntegerField(read_only=True, allow_null=True)
    total_marks = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    computed_marks = serializers.DecimalField(max_digits=9, decimal_places=2, read_only=True)
    matches_total = serializers.BooleanField(read_only=True)
    pass_marks = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)
    problems = serializers.ListField(child=serializers.CharField(), read_only=True)
    parts = ExamPaperPartSerializer(many=True, read_only=True)

    def to_representation(self, exam):
        # `sections.all()` and not `.filter()`/`.order_by()`: anything else
        # bypasses the detail view's prefetch and re-queries per exam.
        return super().to_representation(services.paper_header(exam=exam, sections=exam.sections.all()))


# -- exams -------------------------------------------------------------------


class AdminExamSerializer(MergedAttrsMixin, serializers.ModelSerializer):
    batch_id = serializers.PrimaryKeyRelatedField(
        source="batch", queryset=Batch.objects.all(), required=False, allow_null=True, default=None
    )
    batch_name = serializers.CharField(source="batch.name", read_only=True, default=None)
    #: What the paper contains, derived from its sections. Replaces the old
    #: `exam_type` enum, which had one member per *combination* of question
    #: types and so could not survive a third type.
    question_types = serializers.SerializerMethodField()
    created_by_id = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)

    #: Annotated on the queryset rather than stored -- see `views.exam_queryset`.
    section_count = serializers.IntegerField(read_only=True, default=0)
    selected_question_count = serializers.IntegerField(read_only=True, default=0)
    computed_marks = serializers.DecimalField(max_digits=9, decimal_places=2, read_only=True, default=None)

    class Meta:
        model = Exam
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "instructions",
            "question_types",
            "status",
            "scope",
            "batch_id",
            "batch_name",
            "created_by_id",
            "created_by_name",
            "total_marks",
            "pass_marks",
            "duration_minutes",
            "start_time",
            "end_time",
            "result_publish_time",
            "max_attempts",
            "section_count",
            "selected_question_count",
            "computed_marks",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.ChoiceField(choices=ExamSection.Type.choices)))
    def get_question_types(self, exam):
        # `sections.all()` off the prefetch, never `.values_list()`, which
        # would re-query once per row on the list.
        seen = []
        for section in exam.sections.all():
            if section.question_type not in seen:
                seen.append(section.question_type)
        return seen

    def validate(self, attrs):
        attrs = super().validate(attrs)
        after = self.merged(attrs)

        services.validate_exam(
            total_marks=after("total_marks"),
            pass_marks=after("pass_marks"),
            max_attempts=after("max_attempts"),
            duration_minutes=after("duration_minutes"),
            start_time=after("start_time"),
            end_time=after("end_time"),
            result_publish_time=after("result_publish_time"),
        )
        services.validate_exam_scope(scope=after("scope", Exam.Scope.STANDALONE), batch=after("batch"))
        # A published paper is frozen on the columns the publish check reasons
        # about; renaming or rescheduling one stays fine.
        services.validate_published_edit(instance=self.instance, attrs=attrs)

        becoming_published = after("status", Exam.Status.DRAFT) == Exam.Status.PUBLISHED and (
            self.instance is None or self.instance.status != Exam.Status.PUBLISHED
        )
        if becoming_published:
            if self.instance is None:
                raise serializers.ValidationError(
                    {"status": "An exam needs at least one section before it can be published."}
                )
            # Checked against the exam as it *will be*, not as it was stored: a
            # PATCH may raise `total_marks` and publish in the same request, and
            # comparing the sections against the stale total would reject it.
            prospective = copy.copy(self.instance)
            for field in ("total_marks", "scope", "start_time"):
                setattr(prospective, field, after(field))
            services.validate_publish(exam=prospective, sections=self.instance.sections.all())
        return attrs


class AdminExamDetailSerializer(AdminExamSerializer):
    sections = ExamSectionRowSerializer(many=True, read_only=True)
    #: Detail only. The list is pinned at four queries by two tests, and a
    #: header needs every section of every row on the page.
    paper = ExamPaperHeaderSerializer(source="*", read_only=True)

    class Meta(AdminExamSerializer.Meta):
        fields = [*AdminExamSerializer.Meta.fields, "paper", "sections"]


# -- the picker --------------------------------------------------------------


class ExamSectionQuestionBulkSerializer(serializers.Serializer):
    """`PUT`/`POST`/`DELETE` body for `exam-sections/<pk>/questions/`."""

    block_ids = serializers.PrimaryKeyRelatedField(queryset=QuestionBlock.objects.all(), many=True, allow_empty=True)
    mode = serializers.ChoiceField(choices=["append", "replace"], default="append")

    def validate(self, attrs):
        """The composition rules run here, not in `save()`.

        A Django `ValidationError` raised inside `save()` is outside DRF's
        `run_validation`, so nothing converts it and it escapes the handler as
        a 500 instead of the 422 it is. Removing a block needs no such check,
        so `check_blocks` turns it off for DELETE.
        """
        attrs = super().validate(attrs)
        section = self.context.get("section")
        if section is not None and self.context.get("check_blocks", True):
            services.validate_section_blocks(section=section, blocks=attrs["block_ids"])
        return attrs

    @transaction.atomic
    def save(self, *, section, mode=None):
        """Keep the picks that are still picked; add and drop only the rest.

        Emphatically **not** delete-everything-then-recreate. A pick owns its
        marks -- a bonus question priced at 2 on a section otherwise worth 1 is
        a supported thing to do -- and wiping the rows reset every one of them
        to the section rate. Re-opening the picker and saving without changing
        anything silently undid a teacher's pricing.

        It also keeps each row's id, which nothing reads yet but a submission's
        answer will; the question app learned the same lesson about option ids.
        """
        blocks = self.validated_data["block_ids"]
        replacing = (mode or self.validated_data["mode"]) == "replace"

        existing = {pick.block_id: pick for pick in section.section_questions.all()}

        if replacing:
            kept = {block.pk for block in blocks}
            section.section_questions.exclude(block_id__in=kept).delete()

        # Appending an already-picked block is a no-op rather than a unique
        # violation: the same request twice must not be a 500.
        added = [block for block in blocks if block.pk not in existing]

        # A replace numbers the new rows by where they sit in the *paper*, not
        # by their index among the new ones. Numbering them among themselves
        # put an inserted question on a position a survivor had never moved
        # off -- picking [A, B] and then replacing with [A, C, B] left A and C
        # both on 0 and position 1 empty. An append has no survivors to
        # collide with, so it carries on after the rows already there.
        if replacing:
            position = {block.pk: order for order, block in enumerate(blocks)}
        else:
            position = {block.pk: len(existing) + offset for offset, block in enumerate(added)}

        # Priced by what the block actually asks of a student: a passage with
        # three MCQs costs three times the rate, while a four-part সৃজনশীল
        # costs it once. The pick owns its marks from here, so a deliberate
        # override survives the next save.
        ExamSectionQuestion.objects.bulk_create(
            ExamSectionQuestion(
                section=section,
                block=block,
                marks=services.block_question_count(block, section.question_type) * section.marks_per_question,
                order=position[block.pk],
            )
            for block in added
        )

        if replacing:
            # The picked order is the paper's order, so survivors move rather
            # than keeping whatever position they used to hold.
            moved = []
            for order, block in enumerate(blocks):
                pick = existing.get(block.pk)
                if pick is not None and pick.order != order:
                    pick.order = order
                    moved.append(pick)
            if moved:
                ExamSectionQuestion.objects.bulk_update(moved, ["order"])

        # `bulk_create` and `bulk_update` skip signals, so the counters are
        # this call's job.
        services.sync_section_totals(section)
        return section
