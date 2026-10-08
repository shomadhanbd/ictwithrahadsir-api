from rest_framework import serializers

from apps.academic.models import Batch, Subject
from apps.exam import selectors, validators
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.selectors import assert_may_author_exam
from apps.question.models import QuestionBlock


class MergedAttrsMixin:
    """Reads a field as it will be once this request is applied."""

    def merged(self, attrs):
        def after(field, default=None):
            return attrs.get(field, getattr(self.instance, field, default))

        return after


class ExamSectionQuestionRowSerializer(serializers.ModelSerializer):
    """The lightweight row nested in an exam's detail."""

    class Meta:
        model = ExamSectionQuestion
        fields = ["id", "block_id", "marks", "order"]


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
        if self.instance is not None and "exam" in attrs and attrs["exam"] != self.instance.exam:
            raise serializers.ValidationError({"exam_id": "A section cannot be moved to another exam."})
        assert_may_author_exam(self.context["request"].user, exam)
        validators.validate_paper_is_editable(exam)

        question_type = after("question_type", ExamSection.Type.MCQ)
        subject = after("subject")

        if self.instance is not None:
            validators.validate_question_type_change(section=self.instance, question_type=question_type)
            validators.validate_section_subject_change(section=self.instance, subject=subject)

        validators.validate_section(
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
    negative_marks = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True)
    pass_marks = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True, allow_null=True)
    problems = serializers.ListField(child=serializers.CharField(), read_only=True)


class ExamPaperHeaderSerializer(serializers.Serializer):
    """What the top of the প্রশ্নপত্র says."""

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
        return super().to_representation(selectors.paper_header(exam=exam, sections=exam.sections.all()))


class AdminExamSerializer(MergedAttrsMixin, serializers.ModelSerializer):
    batch_id = serializers.PrimaryKeyRelatedField(
        source="batch", queryset=Batch.objects.all(), required=False, allow_null=True, default=None
    )
    batch_name = serializers.CharField(source="batch.name", read_only=True, default=None)
    question_types = serializers.SerializerMethodField()
    lesson = serializers.SerializerMethodField()
    created_by_id = serializers.IntegerField(read_only=True)
    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)

    section_count = serializers.IntegerField(read_only=True, default=0)
    selected_question_count = serializers.IntegerField(read_only=True, default=0)
    computed_marks = serializers.DecimalField(max_digits=9, decimal_places=2, read_only=True, default=None)
    attempt_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Exam
        fields = [
            "id",
            "title",
            "description",
            "instructions",
            "question_types",
            "status",
            "scope",
            "batch_id",
            "batch_name",
            "lesson",
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
            "attempt_count",
        ]

    def get_lesson(self, exam) -> dict | None:
        lesson = exam.lesson if exam.lesson_id else None
        if lesson is None:
            return None
        return {
            "id": lesson.pk,
            "title": lesson.title,
            "section_id": lesson.section_id,
            "course_id": lesson.course_id,
            "course_title": lesson.course.title,
        }

    def get_question_types(self, exam):
        seen = []
        for section in exam.sections.all():
            if section.question_type not in seen:
                seen.append(section.question_type)
        return seen

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None:
            raise serializers.ValidationError({"scope": "Create exams as lessons inside a course."})
        validators.validate_exam_update(self.instance, attrs, self.merged(attrs))
        return attrs


class AdminExamDetailSerializer(AdminExamSerializer):
    sections = ExamSectionRowSerializer(many=True, read_only=True)
    paper = ExamPaperHeaderSerializer(source="*", read_only=True)

    class Meta(AdminExamSerializer.Meta):
        fields = [*AdminExamSerializer.Meta.fields, "paper", "sections"]


class ExamSectionQuestionBulkSerializer(serializers.Serializer):
    """`PUT exam-sections/<pk>/questions/`: the section's questions, in order."""

    block_ids = serializers.PrimaryKeyRelatedField(queryset=QuestionBlock.objects.all(), many=True, allow_empty=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        section = self.context.get("section")
        if section is not None:
            validators.validate_section_blocks(section=section, blocks=attrs["block_ids"])
        return attrs


def _attempt_row(attempt) -> dict:
    return {
        "id": attempt.pk,
        "user": {"id": attempt.user_id, "name": attempt.user.name, "phone": attempt.user.phone},
        "number": attempt.number,
        "status": attempt.status,
        "is_official": attempt.is_official,
        "awaiting_marking": attempt.awaiting_marking,
        "score": attempt.score,
        "correct": attempt.correct,
        "wrong": attempt.wrong,
        "skipped": attempt.skipped,
        "started_at": attempt.started_at,
        "submitted_at": attempt.submitted_at,
        "time_taken_seconds": attempt.time_taken_seconds,
    }


def exam_attempts_header(exam, *, stats) -> dict:
    """What the submissions table shows above its rows: the exam and the official results' summary."""
    return {
        "exam": {
            "id": exam.pk,
            "title": exam.title,
            "total_marks": exam.total_marks,
            "pass_marks": exam.pass_marks,
            "status": exam.status,
        },
        "summary": stats,
    }


def attempt_rows(attempts, *, ranks) -> list:
    """One page of the submissions table, each attempt with its rank among everyone's official results."""
    return [{**_attempt_row(a), "rank": ranks.get(a.pk)} for a in attempts]


def attempt_review_payload(exam, attempt) -> dict:
    return {
        **_attempt_row(attempt),
        "total_marks": exam.total_marks,
        "questions": selectors.attempt_review(attempt),
        "written": selectors.written_review(attempt, reveal_answers=True),
    }


class WrittenMarkSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    marks = serializers.DecimalField(max_digits=6, decimal_places=2)


class WrittenMarksSerializer(serializers.Serializer):
    marks = WrittenMarkSerializer(many=True, allow_empty=False)
