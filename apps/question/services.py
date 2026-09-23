"""Authoring rules for the question bank.

Here rather than in `Model.clean()` alone because `clean()` is not called by
`save()`, `bulk_create` or a DRF serializer -- the reference app put its
validation there and it never ran on the paths that mattered. Serializers call
these directly; the models call them from `clean()` so the Django admin is
covered too.

What each *type* of question needs is declared in `apps.question.types`, not
branched on here: adding a type should be a registry entry, not a new `if`.
"""

from django.core.exceptions import ValidationError

from apps.question import types
from apps.question.models import Question, QuestionBlock


def validate_block(*, subject, chapter, kind, has_set, has_standalone, topics=()):
    """The block's own consistency: its chapter, its topics, and what its `kind` promises."""
    if chapter is not None and chapter.subject_id != subject.pk:
        raise ValidationError({"chapter": "That chapter belongs to a different subject."})

    # The Question Bank files a block under its topics, so one from another
    # chapter would show up in a folder it does not belong in.
    for topic in topics:
        if chapter is None or topic.chapter_id != chapter.pk:
            raise ValidationError({"topic_ids": f"“{topic.name}” is not a topic of this question's chapter."})

    if kind == QuestionBlock.Kind.GROUP and has_standalone:
        raise ValidationError({"kind": "A group block holds a stimulus set, not one question."})
    if kind == QuestionBlock.Kind.STANDALONE and has_set:
        raise ValidationError({"kind": "A standalone block holds one question, not a stimulus set."})


def validate_owner_kind(*, block=None, question_set=None):
    """A block's `kind` has to agree with what is hung off it.

    Checked here rather than only when the block itself is saved: a stimulus
    set or a question can be created long afterwards, through the API, the
    admin or a shell, and each of those is a way to contradict the `kind`.
    """
    if block is not None and block.kind != QuestionBlock.Kind.STANDALONE:
        raise ValidationError({"block_id": "That block is a group; its questions belong to its stimulus set."})
    if question_set is not None and question_set.block.kind != QuestionBlock.Kind.GROUP:
        raise ValidationError({"question_set_id": "A stimulus set belongs to a group block, not a standalone one."})


def validate_set_block(block):
    """A stimulus set only belongs on a group block."""
    if block is not None and block.kind != QuestionBlock.Kind.GROUP:
        raise ValidationError({"block": "A stimulus set belongs to a group block."})


def validate_question(*, question_type, metadata, options):
    """What a question of this type needs before it can be marked.

    An MCQ with nothing marked correct is the reference app's A5: an empty
    answer compares equal to an empty correct-set and scores full marks. Refuse
    it at authoring, where it is one message rather than a silent wrong mark.

    `options` is the set the question will *end up with* -- on a partial update
    that does not mention options, the caller passes the existing ones, so
    editing a prompt does not require resending the answer key.
    """
    kind = types.kind(question_type)
    settings = types.clean_metadata(question_type, metadata)

    # Checked for every type, not just the ones with an answer key:
    # `(question, position)` is unique, so a duplicate is a 500 from the
    # database rather than a message.
    positions = [option.get("position", 0) for option in options]
    if len(positions) != len(set(positions)):
        raise ValidationError({"options": "Two options share a position."})

    if not kind.uses_options:
        if options:
            raise ValidationError({"options": f"A {kind.label.lower()} takes no options."})
        return

    correct = [option for option in options if option.get("is_correct")]
    if not correct:
        raise ValidationError({"options": "An MCQ needs at least one correct option."})
    if settings.get("select_mode") == "single" and len(correct) > 1:
        raise ValidationError({"options": "A single-answer MCQ cannot have more than one correct option."})


# -- questions already on an exam ----------------------------------------------
#
# A block placed on an exam paper is shared with that paper: the exam checks
# its subject and type when it is placed, and counts its parts. Editing those
# here afterwards would quietly break the paper. The exam app depends on this
# one, not the other way round, so the placements are read through the
# reverse relation (`exam_usages`) and the status by value, not by import.

PUBLISHED = "published"


def exam_placement(block, *, published_only=False):
    """The first exam section this block is placed on, or None."""
    if block is None or block.pk is None:
        return None
    placements = block.exam_usages.select_related("section__exam")
    if published_only:
        placements = placements.filter(section__exam__status=PUBLISHED)
    return placements.first()


def validate_block_change(block, *, subject, kind):
    """A placed block keeps the subject and shape the exam accepted it with."""
    if block is None or (subject.pk == block.subject_id and kind == block.kind):
        return
    placement = exam_placement(block)
    if placement is not None:
        field = "subject_id" if subject.pk != block.subject_id else "kind"
        raise ValidationError(
            {field: f"This question is on the exam “{placement.section.exam.title}”. Take it off the paper first."}
        )


def validate_type_change(block, *, before, after):
    """A placed block's parts keep the type its exam section holds."""
    if before == after:
        return
    placement = exam_placement(block)
    if placement is not None:
        raise ValidationError(
            {
                "question_type": (
                    f"This question is on the exam “{placement.section.exam.title}”. Take it off the paper first."
                )
            }
        )


def validate_new_part_type(block, question_type):
    """A part added to a placed block has to be the type its exam section holds."""
    placement = exam_placement(block)
    if placement is not None and placement.section.question_type != question_type:
        raise ValidationError(
            {
                "question_type": (
                    f"This question is on the exam “{placement.section.exam.title}”, "
                    f"in a {placement.section.get_question_type_display()} section."
                )
            }
        )


def validate_parts_change(block):
    """A published paper's questions keep the parts it was published with.

    Wording, marks and the answer key stay editable -- a typo or a wrong key on
    a live paper has to be fixable -- but adding, removing or moving a part
    changes what the paper asks.
    """
    placement = exam_placement(block, published_only=True)
    if placement is not None:
        raise ValidationError(
            {
                "question_set_id": (
                    f"This question is on the published exam “{placement.section.exam.title}”. "
                    "Move the exam back to draft before adding or removing parts."
                )
            }
        )


def owning_block(*, block=None, question_set=None):
    """The block a question hangs off, whichever side of the xor it uses."""
    return block if block is not None else (question_set.block if question_set is not None else None)


def sync_question_count(block):
    """Recompute `QuestionBlock.question_count` from what is actually there.

    Driven by signals on `Question`, so it holds however the question was
    written -- serializer, Django admin or shell. The reference app moved these
    only when a backfill script ran, so an admin edit left them stale.

    Recomputed rather than incremented: an increment that misses one path
    drifts silently, and this count is small enough that correctness is free.
    """
    if block is None:
        return 0

    if block.kind == QuestionBlock.Kind.GROUP:
        count = Question.objects.filter(question_set__block=block).count()
    else:
        count = Question.objects.filter(block=block).count()

    if block.question_count != count:
        block.question_count = count
        block.save(update_fields=["question_count"])
    return count
