"""Authoring rules for exams.

Here rather than in `Model.clean()` alone, because `clean()` is not called by
`save()`, `bulk_create` or a DRF serializer. Serializers call these directly;
the models call them from `clean()` so the Django admin is covered too.

Every rule raises `ValidationError` with a **dict**. That is load-bearing: the
project's exception handler answers 422 with an `errors` map for a dict detail
and a bare 400 for anything else, and the key is what the frontend anchors the
message to.
"""

import hashlib
import random
from collections import defaultdict, namedtuple
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.question import types as question_types
from apps.question.models import Question

ZERO = Decimal("0")

#: What a published paper may not change without going back to draft. These are
#: the columns the publish check reasons about; everything else -- title, the
#: schedule, shuffling -- stays editable on a live exam.
FROZEN_ONCE_PUBLISHED = ("total_marks", "scope", "batch")


# -- the exam itself ---------------------------------------------------------


def _validate_negative_marks_sign(negative_marks):
    """The sign convention, which the exam and its sections both carry.

    Stated once: the same sentence in two places is the one that drifts.
    """
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
):
    """Configuration that must hold whatever the paper ends up containing."""
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
    closes_at = end_time or start_time
    if result_publish_time and closes_at and result_publish_time < closes_at:
        raise ValidationError({"result_publish_time": "Results cannot be published before the exam ends."})


def validate_exam_scope(*, scope, batch):
    """One scope, and the column that scope needs.

    A third scope means a nullable column, a member on `Exam.Scope`, and a
    branch here.
    """
    if scope == Exam.Scope.STANDALONE:
        if batch is not None:
            raise ValidationError({"scope": "A standalone exam is not attached to a batch."})
    elif batch is None:
        raise ValidationError({"batch_id": "A batch exam needs a batch."})


# -- sections ----------------------------------------------------------------


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
    """What a section may be, given the exam it belongs to.

    Three separate questions, asked in order: are the numbers sane on their
    own, does the question type allow them, and does the section fit inside
    the paper.

    No rule about the paper's own type: a paper *is* the types of its sections,
    so any section type is admissible and adding one to the bank needs no
    change here.
    """
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
    """What the question type allows, asked of the registry rather than of `mcq`."""
    kind = question_types.kind(question_type)

    _validate_negative_marks_sign(negative_marks)
    if negative_marks is not None:
        if marks_per_question is not None and negative_marks > marks_per_question:
            raise ValidationError({"negative_marks": "A wrong answer cannot cost more than a right one is worth."})
        # A positive value, not any value: a form posting "0.00" for every
        # section uniformly must not be told off for a no-op.
        if negative_marks > ZERO and not kind.auto_graded:
            raise ValidationError(
                {"negative_marks": f"Nothing can auto-mark a {kind.label.lower()}, so it cannot be negatively marked."}
            )

    if shuffle_options and not kind.uses_options:
        raise ValidationError({"shuffle_options": f"A {kind.label.lower()} has no options to shuffle."})


def _validate_section_fits_exam(*, exam, subject, marks, duration_minutes, instance):
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

    # `Subject` is a (name, class_level, group) triple and a `Batch` names a
    # class level, so "HSC Physics on an SSC-2027 paper" is catchable here.
    if (
        exam.scope == Exam.Scope.BATCH
        and exam.batch_id
        and subject is not None
        and subject.class_level_id != exam.batch.class_level_id
    ):
        raise ValidationError({"subject_id": "That subject is not taught at this batch's class level."})


def validate_question_type_change(*, section, question_type):
    """The type rule, guarded from the other side.

    Refusing a CQ block in an MCQ section is only half of it: switching the
    section's own type afterwards would contradict every block already in it.
    """
    if question_type != section.question_type and section.question_count:
        raise ValidationError(
            {"question_type": ("Remove this section's questions first -- they are the wrong type for the new one.")}
        )


def validate_section_subject_change(*, section, subject):
    """Same shape as the type rule, for the subject."""
    if subject is None or subject.pk == section.subject_id:
        return
    if section.blocks.exclude(subject=subject).exists():
        raise ValidationError({"subject_id": "Remove this section's questions first -- they are from another subject."})


# -- the blocks a section may hold -------------------------------------------


def block_question_types(block_ids):
    """`{block_id: {"mcq", "cq"}}` for every block that has any question.

    A `QuestionBlock` has no type of its own: the type lives on its questions,
    which hang off either the block (standalone) or its stimulus set (group).
    `Question`'s xor constraint guarantees exactly one of the two paths, so one
    `Q(...) | Q(...)` reaches every question of every block in **one** query --
    the difference between one statement and one per block on a 30-block add.
    """
    rows = (
        Question.objects.filter(Q(block_id__in=block_ids) | Q(question_set__block_id__in=block_ids))
        .annotate(owner_block_id=Coalesce("block_id", "question_set__block_id"))
        .values_list("owner_block_id", "question_type")
        .distinct()
    )
    types = defaultdict(set)
    for block_id, question_type in rows:
        types[block_id].add(question_type)
    return types


def block_question_count(block, question_type):
    """How many questions this block puts on a paper of this type.

    A block is one item to place, not always one question to answer: a passage
    of three MCQs is three, the ক/খ/গ/ঘ of one সৃজনশীল are one.

    Reads `block.question_count` without a query, so a block built in this
    process and not re-read is stale. Both picker paths load theirs from the
    database via a `PrimaryKeyRelatedField`.
    """
    if question_types.kind(question_type).counts_each_part:
        return block.question_count
    return 1


def validate_section_blocks(*, section, blocks):
    """Every reason a block may not go on this section's paper.

    Costs two queries however many blocks are passed: one for their types, one
    for the sibling-section check. Each message names the block, because a
    30-item add that fails with "a block is wrong" is unusable.
    """
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
        raise ValidationError(
            {"block_ids": (f"Block #{clash.block_id} is already in section “{clash.section.title}”.")}
        )


# -- marking -----------------------------------------------------------------

#: A value object rather than a bare tuple: when grading arrives it has to
#: freeze the scheme onto the attempt, and `._asdict()` is that snapshot.
SectionMarking = namedtuple("SectionMarking", "positive negative")


def section_marking(section, *, exam=None):
    """The rates that actually apply to one part of a paper.

    Both are the section's own. A type nothing can auto-mark is never
    negatively marked, so a সৃজনশীল part is 0 however it was filled in -- asked
    of `apps.question.types`, because reading `!= MCQ` would also drop it from
    fill-in-the-blank and ordering, which *are* auto-graded.

    `exam` is unused, kept so callers holding one need not drop it.
    """
    positive = section.marks_per_question

    if not question_types.kind(section.question_type).auto_graded:
        return SectionMarking(positive, ZERO)
    # NULL and 0 mean the same thing now -- there is no paper rate to inherit.
    return SectionMarking(positive, section.negative_marks or ZERO)


# -- publishing --------------------------------------------------------------


def section_problems(section):
    """What is wrong with one part, as `(error key, message)` pairs.

    Split out of `validate_publish` so the paper header can *show* the same
    sentences the publish button would refuse with. Two lists of "what is wrong
    with this exam" would drift within a week.
    """
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

    if exam.scope != Exam.Scope.STANDALONE and exam.start_time is None:
        yield "start_time", "A batch exam needs a start time before it is published."


def validate_paper_is_editable(exam):
    """Refuses a structural change to a published paper.

    `validate_publish` used to be the only guard, and it sat on the exam
    serializer alone -- so a live paper could be gutted through the section and
    picker endpoints, which never looked at `status`. Publishing validated once
    and then watched the wrong door.
    """
    if exam is not None and exam.status == Exam.Status.PUBLISHED:
        raise ValidationError(
            {"status": "This exam is published. Move it back to draft before changing its questions."}
        )


def validate_published_edit(*, instance, attrs):
    """The same freeze, for the exam's own columns.

    Only the fields the publish check reasons about: a published paper can
    still be renamed or rescheduled, which is the other half of the old bug --
    renaming one failed with an error about section marks.
    """
    if instance is None or instance.status != Exam.Status.PUBLISHED:
        return
    # A request that is itself leaving `published` is how you unfreeze.
    if attrs.get("status", Exam.Status.PUBLISHED) != Exam.Status.PUBLISHED:
        return

    for field in FROZEN_ONCE_PUBLISHED:
        if field in attrs and attrs[field] != getattr(instance, field):
            raise ValidationError({field: "This exam is published. Move it back to draft before changing this."})


def validate_publish(*, exam, sections):
    """Everything that may be wrong only once the paper is meant to be final.

    Mostly keyed on `status` rather than on the offending number: none of these
    can be fixed on the publish control itself, so the message carries the
    detail. Raises the first problem, section-by-section first, exactly as it
    did before the generators were split out.
    """
    sections = list(sections)

    for section in sections:
        for key, message in section_problems(section):
            raise ValidationError({key: message})

    for key, message in paper_problems(exam=exam, sections=sections):
        raise ValidationError({key: message})


# -- the paper header --------------------------------------------------------


def paper_header(*, exam, sections):
    """The block a printed প্রশ্নপত্র carries, as domain values.

    Derived, never stored: a stored copy would be the next counter to drift.
    Shows the **declared** numbers, because that is what the paper prints, with
    the computed counterpart beside each and `problems` carrying the very
    sentences the publish button would refuse with.

    Never queries and never raises. Pass `sections` already loaded, off a
    prefetch, or it is the N+1.
    """
    sections = list(sections)
    parts = [_paper_part(section, exam=exam) for section in sections]

    computed = sum((section.target_marks for section in sections), ZERO)
    return {
        "title": exam.title,
        "instructions": exam.instructions,
        "duration_minutes": exam.duration_minutes,
        "total_marks": exam.total_marks,
        "computed_marks": computed,
        "matches_total": computed == exam.total_marks,
        "pass_marks": exam.pass_marks,
        "problems": [message for _, message in paper_problems(exam=exam, sections=sections)],
        "parts": parts,
    }


def _paper_part(section, *, exam):
    """One part's line under the paper's heading."""
    answers_required = section.answers_required

    return {
        "section_id": section.pk,
        "title": section.title,
        #: The part's own rubric -- "৬টি প্রশ্নের উত্তর দাও" under a সৃজনশীল
        #: heading. Sits beside the exam's paper-wide নির্দেশনা; they print in
        #: different places and neither replaces the other.
        "instructions": section.instructions,
        "question_type": section.question_type,
        "question_type_label": ExamSection.Type(section.question_type).label,
        "subject_name": section.subject.name if section.subject_id else "",
        "duration_minutes": section.duration_minutes,
        "questions_given": section.question_count,
        "answers_required": answers_required,
        "marks_per_question": section.marks_per_question,
        "marks": section.marks,
        "computed_marks": section.computed_marks,
        "target_marks": section.target_marks,
        #: Whether "১ ✕ 25 = 25 মার্ক" is actually true. A pick may be repriced
        #: off the section rate -- 29 at 1 mark and one at 2 -- and a header
        #: printing a sum that does not add up is worse than one that prints
        #: only the total.
        "shows_multiplication": section.marks_per_question * answers_required == section.target_marks,
        "negative_marks": section_marking(section, exam=exam).negative,
        "pass_marks": section.pass_marks,
        "problems": [message for _, message in section_problems(section)],
    }


# -- shuffling ---------------------------------------------------------------


def paper_seed(*, exam_id, user_id):
    """A per-student seed for one paper, stable across reloads and restarts.

    Not `hash()`, which Python salts per process -- that would reshuffle every
    paper on each deploy.

    Derived rather than stored because there is no attempt row yet. When one
    arrives the seed belongs on it: that is what makes a second attempt differ
    from the first.
    """
    digest = hashlib.blake2b(f"{exam_id}:{user_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def shuffled_picks(picks, *, seed):
    """One section's picks in a per-student order.

    A pick is a *block*, so a passage (উদ্দীপক) travels with its own questions
    and their ক/খ/গ/ঘ order is never touched -- there is nothing to opt out of.

    Permutes an already-ordered list rather than relaxing an `order_by`, which
    would hand the order back to the database.
    """
    picks = list(picks)
    random.Random(seed).shuffle(picks)
    return picks


def shuffled_options(options, *, seed):
    """One MCQ's options in a per-student order.

    **Not safe on every question.** A choice like "উপরের সবগুলো" or "কোনোটিই নয়"
    reads as nonsense anywhere but last, and nothing on `QuestionOption` says
    which those are. Until an option can declare itself pinned, the caller is
    responsible for not shuffling such a question.
    """
    options = list(options)
    random.Random(seed).shuffle(options)
    return options


# -- counters ----------------------------------------------------------------


def sync_section_totals(section):
    """Recompute a section's counters from the picks actually in it.

    Recomputed, not incremented: an increment that misses one path drifts
    silently, and a section holds tens of rows.

    `question_count` counts **questions, not picks** -- a passage with three
    MCQs is three, while four ক/খ/গ/ঘ parts are one সৃজনশীল question.
    """
    if section is None:
        return 0, ZERO

    if question_types.kind(section.question_type).counts_each_part:
        counter = Coalesce(Sum("block__question_count"), 0)
    else:
        counter = Count("pk")

    totals = ExamSectionQuestion.objects.filter(section=section).aggregate(
        count=counter, marks=Coalesce(Sum("marks"), ZERO)
    )
    count, marks = totals["count"], totals["marks"]

    if section.question_count != count or section.computed_marks != marks:
        section.question_count = count
        section.computed_marks = marks
        section.save(update_fields=["question_count", "computed_marks"])
    return count, marks
