import copy

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.utils import ZERO
from apps.question import kinds
from apps.question.models import Question
from apps.question.selectors import block_question_types

FROZEN_ONCE_PUBLISHED = ("total_marks", "scope", "batch", "lesson")
FROZEN_ONCE_ATTEMPTED = ("total_marks", "pass_marks", "duration_minutes", "start_time", "scope", "batch", "lesson")
RESULT_NEEDS_END = "Set when the exam ends: until then students can still sit it after the results."
ATTEMPTED_MESSAGE = "Students have taken this exam; only the answer key can change (then Regrade)."


def _validate_negative_marks_sign(negative_marks):
    """Negative marks are written as the positive amount to subtract."""
    if negative_marks is not None and negative_marks < ZERO:
        raise ValidationError({"negative_marks": "Negative marking is written as the positive amount to subtract."})


def validate_exam(
    *,
    total_marks,
    pass_marks,
    max_attempts,
    duration_minutes,
    start_time,
    end_time,
    result_publish_time,
    result_needs_end=True,
):
    """Configuration that must hold whatever the paper ends up containing.

    `result_needs_end=False` spares an edit that touches neither time, so an exam saved before that rule
    existed can still be renamed.
    """
    if total_marks is not None and total_marks <= ZERO:
        raise ValidationError({"total_marks": "Total marks must be greater than zero."})
    if pass_marks is not None and total_marks is not None and pass_marks > total_marks:
        raise ValidationError({"pass_marks": "Pass marks cannot exceed total marks."})

    if max_attempts is not None and max_attempts < 1:
        raise ValidationError({"max_attempts": "An exam allows at least one attempt."})
    if duration_minutes is not None and duration_minutes < 1:
        raise ValidationError({"duration_minutes": "An exam runs for at least a minute."})

    if start_time and end_time and end_time <= start_time:
        raise ValidationError({"end_time": "The exam cannot end before it starts."})
    if result_publish_time and end_time is None and result_needs_end:
        raise ValidationError({"result_publish_time": RESULT_NEEDS_END})
    if result_publish_time and end_time is not None and result_publish_time < end_time:
        raise ValidationError({"result_publish_time": "Results cannot be published before the exam ends."})


def validate_exam_scope(*, scope, batch, lesson=None):
    """A batch exam needs a batch, a course exam a lesson, a standalone exam neither."""
    if scope == Exam.Scope.COURSE:
        if lesson is None:
            raise ValidationError({"scope": "A course exam is created by adding an exam lesson to a course."})
        if batch is not None:
            raise ValidationError({"scope": "A course exam is not attached to a batch."})
        return
    if lesson is not None:
        raise ValidationError({"scope": "An exam that belongs to a lesson is a course exam."})
    if scope == Exam.Scope.STANDALONE:
        if batch is not None:
            raise ValidationError({"scope": "A standalone exam is not attached to a batch."})
    elif batch is None:
        raise ValidationError({"batch_id": "A batch exam needs a batch."})


def _sibling_totals(exam, instance):
    """This exam's other sections, as one aggregate."""
    siblings = ExamSection.objects.filter(exam=exam)
    if instance is not None and instance.pk:
        siblings = siblings.exclude(pk=instance.pk)
    return siblings.aggregate(
        marks=Coalesce(Sum("marks"), ZERO),
        minutes=Coalesce(Sum("duration_minutes"), 0),
    )


def validate_section(
    *,
    exam,
    question_type,
    subject,
    marks,
    marks_per_question,
    duration_minutes,
    required_question_count,
    negative_marks=None,
    pass_marks=None,
    shuffle_options=False,
    instance=None,
):
    """What a section may be, given the exam it belongs to."""
    _validate_section_amounts(
        marks=marks,
        marks_per_question=marks_per_question,
        required_question_count=required_question_count,
        pass_marks=pass_marks,
    )
    _validate_section_type_rules(
        question_type=question_type,
        marks_per_question=marks_per_question,
        negative_marks=negative_marks,
        shuffle_options=shuffle_options,
    )
    _validate_section_fits_exam(
        exam=exam,
        subject=subject,
        marks=marks,
        duration_minutes=duration_minutes,
        instance=instance,
        question_type=question_type,
    )


def _validate_section_amounts(*, marks, marks_per_question, required_question_count, pass_marks):
    """Numbers that must hold whatever type the section is, or paper it is on."""
    if marks is not None and marks <= ZERO:
        raise ValidationError({"marks": "A section is worth more than zero marks."})
    if marks_per_question is not None and marks_per_question <= ZERO:
        raise ValidationError({"marks_per_question": "A question is worth more than zero marks."})
    if required_question_count is not None and required_question_count < 1:
        raise ValidationError({"required_question_count": "A section asks for at least one answer."})

    if pass_marks is not None:
        if pass_marks <= ZERO:
            raise ValidationError({"pass_marks": "Pass marks must be greater than zero."})
        if marks is not None and pass_marks > marks:
            raise ValidationError({"pass_marks": "A section's pass marks cannot exceed what it is worth."})


def _validate_section_type_rules(*, question_type, marks_per_question, negative_marks, shuffle_options):
    """What the question type allows."""
    kind = kinds.kind(question_type)

    _validate_negative_marks_sign(negative_marks)
    if negative_marks is not None:
        if marks_per_question is not None and negative_marks > marks_per_question:
            raise ValidationError({"negative_marks": "A wrong answer cannot cost more than a right one is worth."})
        if negative_marks > ZERO and not kind.auto_graded:
            raise ValidationError(
                {"negative_marks": f"Nothing can auto-mark a {kind.label.lower()}, so it cannot be negatively marked."}
            )

    if shuffle_options and not kind.uses_options:
        raise ValidationError({"shuffle_options": f"A {kind.label.lower()} has no options to shuffle."})


def _validate_section_fits_exam(*, exam, subject, marks, duration_minutes, instance, question_type=None):
    """What the section may be, given the other sections already on the paper."""
    totals = _sibling_totals(exam, instance)

    if marks is not None and totals["marks"] + marks > exam.total_marks:
        raise ValidationError(
            {"marks": f"The sections together are worth more than the exam's {exam.total_marks:g} marks."}
        )
    if (
        duration_minutes is not None
        and exam.duration_minutes is not None
        and totals["minutes"] + duration_minutes > exam.duration_minutes
    ):
        raise ValidationError(
            {"duration_minutes": f"The sections together run longer than the exam's {exam.duration_minutes} minutes."}
        )

    if exam.scope == Exam.Scope.COURSE and question_type is not None and question_type != Question.Type.MCQ:
        raise ValidationError({"question_type": "A course exam is taken online, so its parts must be MCQ."})

    if (
        exam.scope == Exam.Scope.BATCH
        and exam.batch_id
        and subject is not None
        and subject.class_level_id != exam.batch.class_level_id
    ):
        raise ValidationError({"subject_id": "That subject is not taught at this batch's class level."})


def validate_question_type_change(*, section, question_type):
    """A section that already holds questions cannot change type."""
    if question_type != section.question_type and section.question_count:
        raise ValidationError(
            {"question_type": "Remove this section's questions first -- they are the wrong type for the new one."}
        )


def validate_section_subject_change(*, section, subject):
    """A section that already holds questions cannot change subject."""
    if subject is None or subject.pk == section.subject_id:
        return
    if section.blocks.exclude(subject=subject).exists():
        raise ValidationError({"subject_id": "Remove this section's questions first -- they are from another subject."})


def validate_section_blocks(*, section, blocks):
    """Every reason a block may not go on this section's paper."""
    ids = [block.pk for block in blocks]
    if len(ids) != len(set(ids)):
        raise ValidationError({"block_ids": "The same question is listed twice."})

    types = block_question_types(ids)
    wanted = section.question_type

    for block in blocks:
        if not block.is_active:
            raise ValidationError({"block_ids": f"Block #{block.pk} is retired and cannot be put on an exam."})
        if block.subject_id != section.subject_id:
            raise ValidationError({"block_ids": f"Block #{block.pk} is not from this section's subject."})
        found = types.get(block.pk)
        if not found:
            raise ValidationError({"block_ids": f"Block #{block.pk} has no questions yet."})
        if found != {wanted}:
            label = ExamSection.Type(wanted).label
            raise ValidationError({"block_ids": f"Block #{block.pk} is not {label} content."})

    clash = (
        ExamSectionQuestion.objects.filter(section__exam_id=section.exam_id, block_id__in=ids)
        .exclude(section_id=section.pk)
        .select_related("section")
        .first()
    )
    if clash is not None:
        raise ValidationError({"block_ids": f"Block #{clash.block_id} is already in section “{clash.section.title}”."})


def validate_pick_marks(*, section, block, marks):
    """An auto-marked section grades every question at its rate, so a pick there costs exactly that.

    A hand-set price would show on the paper but never be what students are marked out of.
    """
    kind = kinds.kind(section.question_type)
    if not kind.auto_graded or marks is None:
        return
    parts = block.question_count if kind.counts_each_part else 1
    if marks != parts * section.marks_per_question:
        raise ValidationError(
            {"marks": "An auto-marked section marks each question at its rate; change the section's rate instead."}
        )


def section_problems(section):
    """What is wrong with one part, as `(error key, message)` pairs."""
    if not section.question_count:
        yield "status", f"Section “{section.title}” has no questions."
        return

    if section.required_question_count and section.required_question_count > section.question_count:
        yield (
            "status",
            f"Section “{section.title}” asks for {section.required_question_count} answers "
            f"but only offers {section.question_count} questions.",
        )
    if section.marks != section.target_marks:
        yield (
            "status",
            f"Section “{section.title}” declares {section.marks:g} marks "
            f"but its questions add up to {section.target_marks:g}.",
        )


def paper_problems(*, exam, sections):
    """What is wrong with the paper as a whole."""
    if not sections:
        yield "status", "An exam needs at least one section before it can be published."
        return

    declared = sum((section.marks for section in sections), ZERO)
    if declared != exam.total_marks:
        yield "status", f"The sections add up to {declared:g}, not the exam's {exam.total_marks:g}."

    if exam.scope == Exam.Scope.BATCH and exam.start_time is None:
        yield "start_time", "A batch exam needs a start time before it is published."

    if exam.result_publish_time and exam.end_time is None:
        yield "result_publish_time", RESULT_NEEDS_END


def validate_paper_is_editable(exam):
    """Refuses a structural change to a published paper, or to any paper students have sat."""
    if exam is not None and exam.pk and exam.attempts.exists():
        raise ValidationError({"status": ATTEMPTED_MESSAGE})
    if exam is not None and exam.status == Exam.Status.PUBLISHED:
        raise ValidationError(
            {"status": "This exam is published. Move it back to draft before changing its questions."}
        )


def validate_attempted_edit(*, instance, attrs):
    """Once students have sat an exam only its wording, attempts allowed and release times may change."""
    if instance is None or not instance.pk or not instance.attempts.exists():
        return
    if attrs.get("status", instance.status) != instance.status:
        raise ValidationError({"status": ATTEMPTED_MESSAGE})
    for field in FROZEN_ONCE_ATTEMPTED:
        if field in attrs and attrs[field] != getattr(instance, field):
            raise ValidationError({field: ATTEMPTED_MESSAGE})
    end_time = attrs.get("end_time", instance.end_time)
    if (
        end_time is not None
        and end_time != instance.end_time
        and end_time < timezone.now()
        and instance.attempts.in_progress().exists()
    ):
        raise ValidationError({"end_time": "Students are sitting this exam; it cannot end before now."})


def validate_published_edit(*, instance, attrs):
    """A published exam cannot change its frozen columns (marks, scope, batch, lesson)."""
    if instance is None or instance.status != Exam.Status.PUBLISHED:
        return
    if attrs.get("status", Exam.Status.PUBLISHED) != Exam.Status.PUBLISHED:
        return

    for field in FROZEN_ONCE_PUBLISHED:
        if field in attrs and attrs[field] != getattr(instance, field):
            raise ValidationError({field: "This exam is published. Move it back to draft before changing this."})


def validate_publish(*, exam, sections):
    """Everything that may be wrong only once the paper is meant to be final; raises the first."""
    sections = list(sections)
    problems = [problem for section in sections for problem in section_problems(section)]
    problems += list(paper_problems(exam=exam, sections=sections))
    if problems:
        key, message = problems[0]
        raise ValidationError({key: message})


def validate_exam_update(instance, attrs, after):
    """Every rule on an exam edit, including the checks a move to published triggers."""
    validate_exam(
        total_marks=after("total_marks"),
        pass_marks=after("pass_marks"),
        max_attempts=after("max_attempts"),
        duration_minutes=after("duration_minutes"),
        start_time=after("start_time"),
        end_time=after("end_time"),
        result_publish_time=after("result_publish_time"),
        result_needs_end="result_publish_time" in attrs or "end_time" in attrs,
    )
    validate_exam_scope(scope=after("scope", Exam.Scope.STANDALONE), batch=after("batch"), lesson=instance.lesson)
    validate_attempted_edit(instance=instance, attrs=attrs)
    validate_published_edit(instance=instance, attrs=attrs)

    if after("status", Exam.Status.DRAFT) == Exam.Status.PUBLISHED and instance.status != Exam.Status.PUBLISHED:
        prospective = copy.copy(instance)
        for field in ("total_marks", "scope", "start_time"):
            setattr(prospective, field, after(field))
        validate_publish(exam=prospective, sections=instance.sections.all())


def validate_may_start(exam, *, used, now):
    if exam.start_time and now < exam.start_time:
        raise ValidationError({"exam": f"This exam opens at {timezone.localtime(exam.start_time):%d %b %Y, %H:%M}."})
    if exam.end_time and now >= exam.end_time:
        raise ValidationError({"exam": "This exam has closed."})
    if used >= exam.max_attempts:
        raise ValidationError({"exam": "You have used all your attempts at this exam."})


def validate_answers(wanted, *, on_paper, valid_options):
    """`wanted` is `{question_id: [option ids]}`; each must be on the paper and use its own options."""
    for question_id in wanted:
        if question_id not in on_paper:
            raise ValidationError({"answers": f"Question {question_id} is not on this paper."})
    for question_id, option_ids in wanted.items():
        _placement, question = on_paper[question_id]
        if not set(option_ids) <= valid_options[question_id]:
            raise ValidationError({"answers": f"An option chosen for question {question_id} is not one of its own."})
        if len(option_ids) > 1 and question.select_mode == "single":
            raise ValidationError({"answers": f"Question {question_id} takes one answer."})


def validate_required_answers(answered, *, sections):
    """`answered` is `{section_id: questions answered}`; an "answer any N" section takes no more than N."""
    for section in sections:
        limit = section.required_question_count
        if limit and answered.get(section.pk, 0) > limit:
            raise ValidationError(
                {"answers": f"Section “{section.title}” takes {limit} answers. Clear one before choosing another."}
            )


def validate_course_exam_deletable(exam):
    if exam.lesson_id is not None:
        raise ValidationError({"exam": "This is a course exam. Delete its lesson instead."})
